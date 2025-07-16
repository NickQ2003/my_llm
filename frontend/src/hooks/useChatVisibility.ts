import { useState } from "react";

export function useChatVisibility() {
  const [chatVisible, setChatVisible] = useState(false);
  return { chatVisible, setChatVisible };
}
