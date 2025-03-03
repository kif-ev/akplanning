from datetime import datetime

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from AKModel.models import AK


def ak_interest_indication_active(event, current_timestamp):
    """
    Check whether indication of interest is currently allowed for a given event

    :param event: event to check for
    :type event: Event
    :param current_timestamp: current timestamp
    :type current_timestamp: datetime
    :return: True if indication is allowed, False if not
    :rtype: Bool
    """
    return (event.active and event.interest_start is not None and event.interest_end is not None
            and event.interest_start <= current_timestamp <= event.interest_end)


@api_view(['POST'])
def increment_interest_counter(request, event_slug, pk, **kwargs):
    """
    Increment interest counter for AK

    This view either returns an HTTP 200 if the counter was incremented,
    an HTTP 403 if indicating interest is currently not allowed,
    or an HTTP 404 if there is no matching AK for the given primary key and event slug.
    """
    try:
        ak = AK.objects.get(pk=pk, event__slug=event_slug)
        # Check whether interest indication is currently allowed
        current_timestamp = datetime.now().astimezone(ak.event.timezone)
        if ak_interest_indication_active(ak.event, current_timestamp):
            ak.interest_counter += 1
            ak.save()
            return Response({'interest_counter': ak.interest_counter}, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_403_FORBIDDEN)
    except AK.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
