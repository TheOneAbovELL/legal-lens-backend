import { formatTime } from "@/lib/utils/format";
import type { ChatMessage } from "./chatReducer";

export function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <article className="msg msg--user" aria-label="Your question" data-testid="user-message">
      <div className="msg__bubble">{message.content}</div>
      <div className="msg__meta"><time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time></div>
    </article>
  );
}
