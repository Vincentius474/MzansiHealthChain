"use client";
import { fmtDate } from "@/lib/format";
import { Notification } from "@/lib/api";

export default function WorkflowNotifications({
  items,
  onRead,
}: {
  items: Notification[];
  onRead: (id: string) => void;
}) {
  return (
    <section>
      <h2>Notifications</h2>
      {items.length === 0 ? (
        <p className="muted">No notifications yet.</p>
      ) : (
        <ul className="list">
          {items.map((item) => (
            <li key={item.id}>
              <span>
                <strong>{item.message}</strong>
                <br />
                <small className="muted">{fmtDate(item.created_at)}</small>
              </span>
              {item.read_at ? (
                <span className="chip">Read</span>
              ) : (
                <button className="secondary" onClick={() => onRead(item.id)}>Mark read</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
