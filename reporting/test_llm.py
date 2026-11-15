"""Tests for the Gemini client. No test makes a real network call: urlopen is mocked."""

import io
import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase, override_settings

from reporting import llm


def fake_response(payload, status=200):
    response = mock.MagicMock()
    response.status = status
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return response


def gemini_reply(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="test-model")
class LLMTests(SimpleTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_generate_text_success_and_request_shape(self, urlopen):
        urlopen.return_value = fake_response(gemini_reply("  Hello  "))
        self.assertEqual(llm.generate_text("hi"), "Hello")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, llm.URL.format(model="test-model"))
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(json.loads(request.data), {"contents": [{"parts": [{"text": "hi"}]}]})

    @mock.patch("urllib.request.urlopen")
    def test_generate_json_asks_for_json_and_parses(self, urlopen):
        urlopen.return_value = fake_response(gemini_reply('{"a": 1}'))
        self.assertEqual(llm.generate_json("hi"), {"a": 1})
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["generationConfig"], {"responseMimeType": "application/json"})

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_raises(self, urlopen):
        urlopen.return_value = fake_response(gemini_reply("not json"))
        with self.assertRaises(llm.LLMError):
            llm.generate_json("hi")

    @mock.patch("urllib.request.urlopen")
    def test_http_error_raises(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError("u", 429, "Too Many", {}, io.BytesIO(b""))
        with self.assertRaises(llm.LLMError):
            llm.generate_text("hi")

    @mock.patch("reporting.llm.time.sleep")
    @mock.patch("urllib.request.urlopen")
    def test_busy_503_is_retried_once(self, urlopen, sleep):
        busy = urllib.error.HTTPError("u", 503, "Busy", {}, io.BytesIO(b""))
        urlopen.side_effect = [busy, fake_response(gemini_reply("hello"))]
        self.assertEqual(llm.generate_text("hi"), "hello")
        self.assertEqual(urlopen.call_count, 2)

        urlopen.reset_mock()
        urlopen.side_effect = [busy, busy, fake_response(gemini_reply("hello"))]
        with self.assertRaises(llm.LLMError):
            llm.generate_text("hi")
        self.assertEqual(urlopen.call_count, 2)

    @mock.patch("urllib.request.urlopen")
    def test_non_200_status_raises(self, urlopen):
        urlopen.return_value = fake_response(gemini_reply("x"), status=500)
        with self.assertRaises(llm.LLMError):
            llm.generate_text("hi")

    @mock.patch("urllib.request.urlopen")
    def test_timeout_and_network_failure_raise(self, urlopen):
        for error in (TimeoutError(), urllib.error.URLError("no network")):
            urlopen.side_effect = error
            with self.assertRaises(llm.LLMError):
                llm.generate_text("hi")

    @mock.patch("urllib.request.urlopen")
    def test_malformed_body_raises(self, urlopen):
        response = fake_response({})
        response.read.return_value = b"<html>oops</html>"
        urlopen.return_value = response
        with self.assertRaises(llm.LLMError):
            llm.generate_text("hi")

    @mock.patch("urllib.request.urlopen")
    def test_empty_or_blocked_response_raises(self, urlopen):
        for payload in ({}, {"candidates": []}, {"promptFeedback": {"blockReason": "SAFETY"}}, gemini_reply("  ")):
            urlopen.return_value = fake_response(payload)
            with self.assertRaises(llm.LLMError):
                llm.generate_text("hi")

    @override_settings(GEMINI_API_KEY="")
    @mock.patch("urllib.request.urlopen")
    def test_not_configured(self, urlopen):
        self.assertFalse(llm.is_configured())
        with self.assertRaises(llm.LLMError):
            llm.generate_text("hi")
        with self.assertRaises(llm.LLMError):
            llm.generate_json("hi")
        urlopen.assert_not_called()
