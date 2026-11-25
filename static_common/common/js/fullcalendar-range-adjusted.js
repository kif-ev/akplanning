/**
 * FullCalendar extension: Timeline view that shows exactly the specified visible range
 *
 * FullCalendar always rounds the visibleRange to full days and then shows each of these days from slotMinTime
 * to slotMaxTime. The view type "resourceTimelineRangeAdjusted" instead starts and ends the timeline exactly
 * at the start and end of the visibleRange (rounded to full hours, since the timeline uses hourly slots),
 * while still hiding the hours outside slotMinTime/slotMaxTime on each day.
 *
 * Usage: Use "resourceTimelineRangeAdjusted" as view type (either directly or as type of a custom view)
 * and specify the visibleRange as an object with start and end.
 *
 * This file has to be loaded after FullCalendar itself, the view is registered for all calendars on the page.
 */
(function () {
    const HOUR_MS = 60 * 60 * 1000;
    const DAY_MS = 24 * HOUR_MS;

    /**
     * Round a date marker down to the last full hour
     * (markers represent the local time in the calendar's timezone as UTC)
     */
    function floorToHour(marker) {
        const rounded = new Date(marker.valueOf());
        rounded.setUTCMinutes(0, 0, 0);
        return rounded;
    }

    /**
     * Round a date marker up to the next full hour
     */
    function ceilToHour(marker) {
        const floored = floorToHour(marker);
        return floored.valueOf() === marker.valueOf() ? floored : new Date(floored.valueOf() + HOUR_MS);
    }

    class RangeAdjustedDateProfileGenerator extends FullCalendar.Internal.DateProfileGenerator {
        /**
         * Is the visible range a static range given as object (functions etc. are handled as usual)?
         */
        hasStaticRange() {
            const {visibleRangeInput} = this.props;
            return Boolean(visibleRangeInput) && typeof visibleRangeInput === 'object'
                && visibleRangeInput.start != null && visibleRangeInput.end != null;
        }

        // A static range cannot be navigated (the previous/next range would be the same again),
        // hence mark it as invalid. This disables the prev/next buttons (as for the today button)
        // and prevents navigation
        buildPrev(currentDateProfile, currentDate, forceToValid) {
            const profile = super.buildPrev(currentDateProfile, currentDate, forceToValid);
            if (this.hasStaticRange()) {
                profile.isValid = false;
            }
            return profile;
        }

        buildNext(currentDateProfile, currentDate, forceToValid) {
            const profile = super.buildNext(currentDateProfile, currentDate, forceToValid);
            if (this.hasStaticRange()) {
                profile.isValid = false;
            }
            return profile;
        }

        build(currentDate, direction, forceToValid = true) {
            const profile = super.build(currentDate, direction, forceToValid);
            const {dateEnv, slotMinTime, slotMaxTime, visibleRangeInput} = this.props;
            if (!this.hasStaticRange()) {
                return profile;
            }
            const rawStart = dateEnv.createMarker(visibleRangeInput.start);
            const rawEnd = dateEnv.createMarker(visibleRangeInput.end);
            if (rawStart === null || rawEnd === null || rawStart >= rawEnd) {
                return profile;
            }
            const start = floorToHour(rawStart);
            const end = ceilToHour(rawEnd);
            // The timeline builds its slots from renderRange.start + slotMinTime
            // to (renderRange.end - 1 day) + slotMaxTime,
            // hence the render range is shifted such that these bounds match the exact start and end.
            // The active range is intentionally kept as is (full days containing the range): FullCalendar uses it
            // for the title and frames events with it (applying slotMinTime/slotMaxTime of the first and last day),
            // which always covers the visible part of the range (setting it to the exact range would drop events,
            // shifting it like the render range would result in a wrong title)
            const asMs = FullCalendar.Internal.asRoughMs;
            profile.renderRange = {
                start: new Date(start.valueOf() - asMs(slotMinTime)),
                end: new Date(end.valueOf() + DAY_MS - asMs(slotMaxTime)),
            };
            return profile;
        }
    }

    FullCalendar.globalPlugins.push(FullCalendar.createPlugin({
        name: 'akplanning-range-adjusted-timeline',
        views: {
            resourceTimelineRangeAdjusted: {
                type: 'resourceTimeline',
                dateProfileGeneratorClass: RangeAdjustedDateProfileGenerator,
            },
        },
    }));
})();
