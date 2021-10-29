from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils.datetime_safe import datetime

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
    return event.active and (event.interest_start is None or (event.interest_start <= current_timestamp and (
            event.interest_end is None or current_timestamp <= event.interest_end)))


@api_view(['POST'])
def increment_interest_counter(request, event_slug, pk, **kwargs):
    """
    Increment interest counter for AK
    """
    ak = AK.objects.get(pk=pk)
    if ak:
        # Check whether interest indication is currently allowed
        current_timestamp = datetime.now().astimezone(ak.event.timezone)
        if ak_interest_indication_active(ak.event, current_timestamp):
            ak.interest_counter += 1
            ak.save()
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_403_FORBIDDEN)
    return Response(status=status.HTTP_404_NOT_FOUND)
