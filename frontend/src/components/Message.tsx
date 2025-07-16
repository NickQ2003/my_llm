type MessageProps = {
  text: string;
  sender: "user" | "bot";
};

const Message = ({ text, sender }: MessageProps) => {
  return (
      <div
          className={`message ${sender === "user" ? "message-user" : "message-bot"}`}
      >
          {text}
      </div>
  );
};

export default Message;
