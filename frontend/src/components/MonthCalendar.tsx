import type {
  CalendarMode,
  OfficialCalendarEvent,
  PersonalizedCalendarEvent,
} from "../api/types";

interface MonthCalendarProps {
  month: string;
  mode: CalendarMode;
  officialEvents: OfficialCalendarEvent[];
  personalizedEvents: PersonalizedCalendarEvent[];
}

const weekDays = ["一", "二", "三", "四", "五", "六", "日"];

export function MonthCalendar({
  month,
  mode,
  officialEvents,
  personalizedEvents,
}: MonthCalendarProps) {
  const [year, monthNumber] = month.split("-").map(Number);
  const dayCount = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const firstWeekDay =
    (new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay() + 6) % 7;
  const cells = Array.from({ length: firstWeekDay + dayCount }, (_, index) =>
    index < firstWeekDay ? null : index - firstWeekDay + 1,
  );

  function itemCount(day: number) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    return mode === "official"
      ? officialEvents.filter((event) => event.end_date === date).length
      : personalizedEvents.filter((event) => event.end_date === date).length;
  }

  return (
    <div
      className="month-calendar"
      aria-label={`${year}年${monthNumber}月日历`}
    >
      <div className="calendar-weekdays" aria-hidden="true">
        {weekDays.map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar-days">
        {cells.map((day, index) => {
          const count = day ? itemCount(day) : 0;
          return (
            <div
              className={`calendar-day ${day ? "" : "calendar-day-empty"}`}
              key={`${day ?? "empty"}-${index}`}
            >
              {day ? (
                <>
                  <span className="calendar-date">{day}</span>
                  {count > 0 ? (
                    <span className="calendar-deadline">{count} 项截止</span>
                  ) : null}
                </>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
