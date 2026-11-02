from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from accounts.models import User

HOME_BY_ROLE = {
    User.Role.STUDENT: "scoring:student_dashboard",
    User.Role.INSTRUCTOR: "grading:instructor_home",
    User.Role.HEAD: "scoring:department_dashboard",
    User.Role.ADMIN: "scoring:department_dashboard",
}


@login_required
def home(request):
    return redirect(HOME_BY_ROLE[request.user.role])
