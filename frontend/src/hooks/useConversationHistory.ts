import { useState, useEffect } from "react";

export function useConversationHistory(model = "openai", sessionId: string | null = null, limit = 10) {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    let url = `http://127.0.0.1:8000/api/conversation/history?model=${model}&limit=${limit}`;
    if (sessionId) url += `&session_id=${sessionId}`;

    fetch(url)
      .then((res) => res.json())
      .then((data) => setHistory(data.history || []))
      .finally(() => setLoading(false));
  }, [model, sessionId, limit]);

  return { history, loading };
}