import json

import celery
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from regulations import tasks
import requests


def upload_proxy(request):
    """Create a random key name and a temporary upload URL to permit uploads
    from the browser.
    """
    try:
        size = int(request.GET['size'])
        assert 0 < size <= settings.ATTACHMENT_MAX_SIZE
    except (KeyError, ValueError, AssertionError):
        return JsonResponse(
            {'message': 'Invalid attachment size'},
            status=400,
        )
    s3 = tasks.make_s3_client()
    key = get_random_string(50)
    url = s3.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'ContentLength': size,
            'ContentType': 'application/octet-stream',
            'Bucket': settings.ATTACHMENT_BUCKET,
            'Key': key,
        },
    )
    return JsonResponse({
        'url': url,
        'key': key,
    })


@csrf_exempt
@require_http_methods(['POST'])
def preview_comment(request):
    body = json.loads(request.body.decode('utf-8'))
    content = tasks.build_comment(body)
    return HttpResponse(content, 'text/markdown', 200)


@csrf_exempt
@require_http_methods(['POST'])
def submit_comment(request):
    """Submit a comment to the task queue."""
    body = json.loads(request.body.decode('utf-8'))
    s3 = tasks.make_s3_client()
    metadata_key = get_random_string(50)
    metadata_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': settings.ATTACHMENT_BUCKET,
            'Key': metadata_key,
        },
    )
    chain = celery.chain(
        tasks.submit_comment.s(body),
        tasks.publish_metadata.s(key=metadata_key),
    )
    chain.delay()
    return JsonResponse({
        'status': 'submitted',
        'metadata_url': metadata_url,
    })


@csrf_exempt
@require_http_methods(['GET', 'HEAD'])
def get_federal_agencies(request):
    response = requests.get(
        settings.REGS_GOV_API_LOOKUP_URL,
        params={'field': 'gov_agency', 'dependentOnValue': 'Federal'},
        headers={'X-Api-Key': settings.REGS_GOV_API_KEY}
    )
    response.raise_for_status()
    return JsonResponse(response.json()['list'], safe=False)


@csrf_exempt
@require_http_methods(['GET', 'HEAD'])
def get_gov_agency_types(request):
    response = requests.get(
        settings.REGS_GOV_API_LOOKUP_URL,
        params={'field': 'gov_agency_type'},
        headers={'X-Api-Key': settings.REGS_GOV_API_KEY}
    )
    response.raise_for_status()
    return JsonResponse(response.json()['list'], safe=False)
