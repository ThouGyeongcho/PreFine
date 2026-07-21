import type {
  CalendarMode,
  OfficialCalendarEvent,
  PersonalizedCalendarEvent,
} from "../api/types";

interface CalendarDetailsProps {
  mode: CalendarMode;
  officialEvents: OfficialCalendarEvent[];
  personalizedEvents: PersonalizedCalendarEvent[];
  sourceUrl: string;
  profileComplete: boolean;
  onShowOfficial: () => void;
}

export function CalendarDetails({
  mode,
  officialEvents,
  personalizedEvents,
  sourceUrl,
  profileComplete,
  onShowOfficial,
}: CalendarDetailsProps) {
  const isOfficial = mode === "official";

  return (
    <section
      className="calendar-details"
      aria-labelledby="calendar-details-title"
    >
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">本月事项</p>
          <h2 id="calendar-details-title">
            {isOfficial ? "官方原文" : "我的税务清单"}
          </h2>
        </div>
        <a
          className="text-link"
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
        >
          查看 12366 来源
        </a>
      </div>

      {!isOfficial && !profileComplete ? (
        <p className="profile-prompt">
          请先在下方完成纳税人身份与税种设置，系统才会生成个性化清单。
        </p>
      ) : null}

      <div className="event-list">
        {isOfficial
          ? officialEvents.map((event) => (
              <article className="event-card" key={event.source_event_id}>
                <p className="event-range">
                  {event.start_date} — {event.end_date}
                </p>
                <p className="official-text">{event.bssz}</p>
                {event.source_agency ? (
                  <p className="muted event-meta">
                    发布：{event.source_agency}
                  </p>
                ) : null}
              </article>
            ))
          : personalizedEvents.map((event) => (
              <article
                className={`event-card ${event.needs_confirmation ? "event-card-warning" : ""}`}
                key={event.key}
              >
                <div className="event-title-row">
                  <strong>{event.display_name}</strong>
                  <span className="event-range">
                    {event.needs_confirmation
                      ? `${event.start_date} — ${event.end_date}`
                      : `截止 ${event.end_date}`}
                  </span>
                </div>
                <p>{event.matched_text}</p>
                {event.needs_confirmation ? (
                  <div className="unknown-event-detail">
                    <span className="muted">对应官方原文</span>
                    <p>{event.official_text}</p>
                    <p className="confirmation-note">
                      该事项暂未匹配到明确税种，请人工确认。
                    </p>
                    <button
                      className="text-button"
                      type="button"
                      onClick={onShowOfficial}
                    >
                      查看官方原文
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
        {(isOfficial ? officialEvents : personalizedEvents).length === 0 ? (
          <p className="empty-list">本月暂无事项。</p>
        ) : null}
      </div>
    </section>
  );
}
