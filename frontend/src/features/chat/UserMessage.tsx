import { formatTime } from "@/lib/utils/format";
import type { ChatMessage } from "./chatReducer";

export function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <article className="turn turn--user" aria-label="Your question" data-testid="user-message">
      <div className="turn__label">
        <span>You</span>
        <time className="turn__time" dateTime={message.createdAt}>{formatTime(message.createdAt)}</time>
      </div>
      <div className="turn__body">{message.content}</div>
    </article>
  );
}
