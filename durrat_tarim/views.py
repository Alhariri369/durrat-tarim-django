from django.shortcuts import render


def error_404(request, exception):
    return render(
        request,
        "404.html",
        {
            "page_title": "الصفحة غير موجودة | درة تريم",
            "robots_content": "noindex,nofollow",
        },
        status=404,
    )
