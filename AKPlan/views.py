import datetime

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView

from AKModel.models import Event, Room, AKSlot
from AKModel.views import EventSlugMixin


class PlanView(EventSlugMixin, TemplateView):
    template_name = 'AKPlan/plan.html'


def clamp(n, smallest, largest):
    return max(smallest, min(n, largest))


def get_red(the_date, is_white, old_hours):
    if the_date:
        now = timezone.now()
        timediff_sec = (now - the_date).total_seconds()
        red = int(clamp(timediff_sec / 3600 / old_hours * 155, 0,155))
    else:
        red = 155
    if is_white:
        return "rgb(%d,%d,%d)" % (255, 100+red, 100+red)
    else:
        return "rgb(%d,%d,%d)" % (255-red, 100, 100)


@xframe_options_exempt
def plan_beamer(request, *args, **kwargs):
    event = Event.get_by_slug("kif475")

    slots = AKSlot.objects.filter(start__isnull=False).order_by('start')
    rooms = Room.objects.filter(event=event).order_by('building', 'name')

    delta = event.end - event.start  # timedelta

    days = [(event.start + datetime.timedelta(i), [], [])
            for i in range(delta.days + 1)]

    pixpersec = 0.0153
    if 'zoom' in request.GET: pixpersec = float(request.GET["zoom"])

    now = timezone.now()
    is_white = False
    if now.hour > 8 and now.hour < 19:
        is_white = True
    if 'bg' in request.GET:
        is_white = True if request.GET['bg'] == 'white' else False

    nowsliderpos = 100
    hoursperday = 15
    daywidth = hoursperday * 3600 * pixpersec
    for daystart, ak_list, hours in days:
        daydate = daystart.date()
        for i in range(0, hoursperday, 2):
            thishour = daystart + datetime.timedelta(hours=i)
            secsfromstart = (thishour - daystart).total_seconds()
            hours.append({'leftpixels': secsfromstart * pixpersec, 'start_time': thishour})
        if daydate < now.date():
            # TODO Hide instead (and make ak wall wider?)
            nowsliderpos += daywidth
        elif now.date() == daydate:
            nowsliderpos += max(0, min(daywidth, ((timezone.localtime(now) - daystart).total_seconds() * pixpersec)))
        for slot in slots:
            if slot.start.date() == daydate:
                secsfromstart = (slot.start - daystart).total_seconds()
                slot.leftpixels = secsfromstart * pixpersec
                slot.widthpixels = datetime.timedelta(hours=float(slot.duration)).total_seconds() * pixpersec - 2
                slot.red = get_red(slot.updated, is_white, 5)

                if slot.leftpixels >= 0:
                    ak_list.append(slot)

    return render(request, "AKPlan/plan_beamer.html", {'title': 'AK Wall', 'days': days, 'rooms': rooms,
                                                       'daywidth': daywidth, 'is_white': is_white,
                                                       'pixpersec': pixpersec, 'nowsliderpos': nowsliderpos})
