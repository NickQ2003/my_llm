import { useState } from "react";
 
type MessageType = {
  text: string;
  sender: "user" | "bot";
};
 
export function useChat() {
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [loading, setLoading] = useState(false);
 
  // Enviar mensaje del usuario
  const sendMessage = async (text: string) => {
    setMessages((prev) => [...prev, { text, sender: "user" }]);
    setLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/chat/openai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      if (data.response) {
        setMessages((prev) => [
          ...prev,
          { text: data.response, sender: "bot" },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { text: "Error: respuesta vacía de la IA.", sender: "bot" },
        ]);
      }
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        { text: `Error al consultar la IA: ${error.message || error}`, sender: "bot" },
      ]);
    }
    setLoading(false);
  };
 
  // Agregar mensaje del bot desde el componente (para archivos)
  const pushBotMessage = (text: string, sender: "bot" | "user" = "bot") => {
    setMessages((prev) => [...prev, { text, sender }]);
  };
 
  return { messages, sendMessage, loading, pushBotMessage, setMessages };
}
 
export default useChat;
 
 