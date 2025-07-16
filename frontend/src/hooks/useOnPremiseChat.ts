import { useState } from "react";
import { sendOnPremiseMessage } from "../services/onPremiseApi";

export const useOnPremiseChat = () => {
  const [messages, setMessages] = useState<{ text: string; sender: "user" | "bot" }[]>([]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (message: string): Promise<void> => {
    if (!message.trim()) return;

    setMessages((prev) => [...prev, { text: message, sender: "user" }]);
    setLoading(true);
    try {
      const response = await sendOnPremiseMessage(message);
      const responseText: string = response || ""; // Aseguramos que sea un string
      setMessages((prev) => [...prev, { text: responseText, sender: "bot" }]);
    } catch (error: any) {
      console.error("Error en onPremiseChat:", error);
      setMessages((prev) => [
        ...prev,
        { text: "Error al conectar con el modelo on-premise.", sender: "bot" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const pushBotMessage = (text: string, sender: "bot" | "user" = "bot") => {
    setMessages((prev) => [...prev, { text, sender }]);
  };
 
  return { messages, sendMessage, loading, pushBotMessage, setMessages };
}

export default useOnPremiseChat;