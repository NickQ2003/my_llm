import { useState, useEffect, useRef } from "react";
import { useChat } from "../hooks/useChat";
import { useChatVisibility } from "../hooks/useChatVisibility";
import { useConversationHistory } from "../hooks/useConversationHistory";
import LoginModal from "./LoginModal";
import ReactMarkdown from "react-markdown";
import AudioQuestion from "./AudioQuestion";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faArrowUp,
  faMagnifyingGlass,
  faMessage,
  faSun,
  faPlus,
  faCircleHalfStroke,
  faSpinner,
} from '@fortawesome/free-solid-svg-icons';
import React from "react";

type ChatProps = {
  onBotonClick: () => void;
};


function Chat({ onBotonClick }: ChatProps) {
  const { messages, sendMessage, loading, pushBotMessage } = useChat();  
  const { chatVisible, setChatVisible } = useChatVisibility();

  // HISTORIAL - SOLO MODIFICADO ESTA LÓGICA
  
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const { history: sessionList, loading: loadingSessions } = useConversationHistory("openai", null, 15);
  const { history: sessionHistory, loading: loadingSessionHistory } = useConversationHistory("openai", selectedSession, 50);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatBoxRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
 
  const [autoScroll, setAutoScroll] = useState(true);
  const [formBajado, setFormBajado] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [MenuOpen, setMenuOpen] = useState(false);
  const [typingText, setTypingText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [message, setMessage] = useState("");
  
  const [isDarkMode, setIsDarkMode] = useState(() => {
    return localStorage.getItem("darkMode") !== "false";
  });

  useEffect(() => {
    if (isDarkMode) {
      document.body.classList.add("dark-mode");
    } else {
      document.body.classList.remove("dark-mode");
    }
    localStorage.setItem("darkMode", String(isDarkMode));
  }, [isDarkMode]);

  const handleSendMessage = () => {
    if (!message.trim() || selectedSession) return;
    sendMessage(message.trim());
    setMessage("");
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    if (!formBajado) setFormBajado(true);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setFileName(file.name);
    }
  };

  const handleSend = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedSession) return; // Solo nuevo chat permite enviar

    let input = event.currentTarget.elements.namedItem("message") as HTMLInputElement;
    if (!input && textareaRef.current) input = textareaRef.current;

    const text = input?.value.trim();

    if (!text && !selectedFile) return;

    if (text) sendMessage(text);

    if (selectedFile) {
      setUploading(true);
      pushBotMessage?.(`Analizando archivo "${selectedFile.name}"...`);

      const formData = new FormData();
      formData.append("file", selectedFile);

      try {
        const res = await fetch("http://127.0.0.1:8000/file/analyze", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        if (data.success) {
          pushBotMessage?.(`**Resumen de "${selectedFile.name}":**\n\n${data.summary || "No se obtuvo resumen."}`);
        } else {
          pushBotMessage?.(`No se pudo analizar el archivo "${selectedFile.name}".\n${data.error || ""}`);
        }
      } catch {
        pushBotMessage?.("Error al subir o analizar el archivo.");
      }

      setSelectedFile(null);
      setFileName(null);
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }

    if (input) input.value = "";
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    if (!formBajado) setFormBajado(true);
  };

  const toggleMenu = () => setMenuOpen(prev => !prev);

  useEffect(() => {
    if (messages.length > 0 && messages[messages.length - 1].sender === "bot") {
      const botMessages = Array.isArray(messages[messages.length - 1].text)
        ? messages[messages.length - 1].text
        : [messages[messages.length - 1].text];

      let currentMessageIndex = 0;
      let currentText = "";
      let i = 0;

      const typeNextMessage = () => {
        if (currentMessageIndex >= botMessages.length) {
          setTypingText("");
          return;
        }

        const botMessage = botMessages[currentMessageIndex].replace(/\n/g, " ");
        if (currentText === "") {
          currentText = "";
          setTypingText(currentText);
        }

        if (i < botMessage.length) {
          currentText += botMessage[i] ?? "";
          setTypingText(currentText);
          i++;
        } else {
          messages[messages.length - 1].text = botMessages[currentMessageIndex];
          currentMessageIndex++;
          currentText = "";
          i = 0;
          setTypingText("");
        }
      };

      const typingInterval = setInterval(typeNextMessage, 15);
      return () => clearInterval(typingInterval);
    }
  }, [messages]);

  useEffect(() => {
    const chatBox = chatBoxRef.current;
    if (!chatBox) return;
    const handleScroll = () => {
      const isAtBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 50;
      setAutoScroll(isAtBottom);
    };
    chatBox.addEventListener("scroll", handleScroll);
    return () => chatBox.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (autoScroll && chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [messages, typingText, autoScroll, sessionHistory]);

  const renderMessageContent = (text: string) => {
    const [intro, ...restParts] = text.split("\n\n");
    const restText = restParts.join("\n\n");

    const renderTable = (tableText: string) => {
      const lines = tableText.trim().split("\n");
      const rows = lines.map(line => line.split("|").map(cell => cell.trim()).filter(Boolean));
      const validRows = rows.filter(row => row.length && !row.every(cell => /^-+$/.test(cell)));
      return (
        <table className="message-table">
          <tbody>
            {validRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    };

    const renderList = (listText: string) => {
      const items = listText.split("\n- ").map(item => item.trim()).filter(Boolean);
      const cleanedItems = items.map((item, index) => index === 0 ? item.replace(/^- /, "") : item);
      return (
        <ul className="message-list">
          {cleanedItems.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      );
    };

    if (restText.includes("|")) {
      const [tableBlock, ...after] = restText.split("\n\n");
      return (
        <>
          {intro && <p>{intro}</p>}
          {renderTable(tableBlock)}
          {after.length > 0 && <p>{after.join("\n\n")}</p>}
        </>
      );
    }

    if (restText.includes("\n- ")) {
      const [listBlock, ...after] = restText.split("\n\n");
      return (
        <>
          {intro && <p>{intro}</p>}
          {renderList(listBlock)}
          {after.length > 0 && <p>{after.join("\n\n")}</p>}
        </>
      );
    }

    return (
      <div>
        {text.split("\n").map((line, index) => (
          <p key={index} style={{ margin: "0.1rem 0" }}>{line}</p>
        ))}
      </div>
    );
  };

  return (
    <div className="app-container">
      {!chatVisible ? (
        <div className="welcome-container">
          <div className="welcome-Logo">
            <img src="/LogoNuevo.png" alt="Logo" className="logo h-10" />
          </div>
            <>
              <h1>¡Bienvenido a Mateo!</h1>
              <h3>Tu asistente virtual</h3>
              <div className="Botones-welcome">
              <button className="start-chat-btn" onClick={() => setChatVisible(true)}>Inicia Chat</button>
              </div>
            </>
        </div>
      ) : (
        <div className="Chat_bot">
          {/* Sidebar y menú */}
          <header>
            <nav>
              <div className="menu-icon" onClick={() => setIsOpen(!isOpen)}>
                <div></div>
                <div></div>
                <div></div>
              </div>
              <div className={`sidebar ${isOpen ? "open" : ""}`}>
                <div className="buttom_slider">
                  <button>
                    <FontAwesomeIcon icon={faMagnifyingGlass} style={{ color: "#ffffff" }} />
                  </button>
                  {/* Nuevo chat (limpia selección de historial) */}
                  <button onClick={() => setSelectedSession(null)}>
                    <FontAwesomeIcon icon={faMessage} style={{ color: "#ffffff" }} />
                  </button>
                </div>
                {/* Historial actualizado */}
                <div className="sections">
                  <div className="section">
                    <h3><FontAwesomeIcon icon={faCircleHalfStroke} /> Chats Recientes</h3>
                    {loadingSessions ? (
                      <p>Cargando...</p>
                    ) : (
                      <ul style={{ maxHeight: 340, overflow: "auto", listStyle: "none", padding: 0 }}>
                        {sessionList.map((conv: any, _idx: number) => (
                          <li
                            key={conv.session_id}
                            onClick={() => setSelectedSession(conv.session_id)}
                            style={{
                              background: conv.session_id === selectedSession ? "#e0e7ff" : undefined,
                              borderRadius: 6,
                              margin: 4,
                              padding: 8,
                              cursor: "pointer"
                            }}
                          >
                            <b>
                              {conv.user_message
                                ? conv.user_message.slice(0, 35) + (conv.user_message.length > 35 ? "..." : "")
                                : "Conversación sin título"}
                            </b>
                            <small style={{ color: "#888" }}>{new Date(conv.timestamp).toLocaleString()}</small>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
                <div className="Ajustes">
             <button onClick={() => setIsDarkMode(!isDarkMode)}>
              <FontAwesomeIcon
               icon={isDarkMode ? faSun : faCircleHalfStroke}
               size="xs"
               style={{ color: isDarkMode ? "#FFD700" : "#ffffff" }}
    />
  </button>
            <button className="Login" onClick={() => setShowLoginModal(true)}>
                   ¡Welcome Ompremise!
            </button>
</div>
              </div>
              <div className={`Chat-Logo ${isOpen ? "mover-derecha" : ""}`}>
                <div className="Menu_Desplegable">
                  <div className="Chat-Logo" onClick={toggleMenu}>
                    <img src="LogoN.png" alt="Logo" className="logo" />

                  </div>
                  {MenuOpen && (
                    <div className="desplegable-contenido">
                      <button onClick={onBotonClick}>
                        <div className="title"><span>Mateo</span>oP</div>
                        <div className="rol"><span>Analistas</span>Digisoc</div>
                      </button>
                    </div>
                  )}
                </div>
                <div className="Boton_Inicio">
                 <button onClick={() => setShowLoginModal(true)}>
                    Login
                 </button>
               </div>
              </div>
            </nav>
          </header>

          {/* Chat */}
          <div ref={chatBoxRef} className={`claude-chat-box ${isOpen ? "mover-chat" : ""}`}>
            {selectedSession ? (
              <>
                {loadingSessionHistory && <div className="Message_Mateo"><p>Cargando conversación...</p></div>}
                {!loadingSessionHistory && sessionHistory.length === 0 && (
                  <div className="Message_Mateo"><p>No hay mensajes en esta sesión.</p></div>
                )}
                {!loadingSessionHistory && sessionHistory.length > 0 && sessionHistory.map((msg: any, idx: number) => (
                  <div key={idx} className="">
                    <div className="message user">Usuario:</div>
                    <div>{msg.user_message}</div>
                    <div style={{ fontWeight: "bold", color: "#3b82f6" }}>Mateo:</div>
                    <div>{msg.chatbot_response}</div>
                    <div style={{ fontSize: 11, color: "#999" }}>{new Date(msg.timestamp).toLocaleString()}</div>
                  </div>
                ))}
              </>
            ) : (
              <>
                {messages.length === 0 && (
                  <div className="Message_Mateo">
                    <p>Hola, soy MATEO, tu asistente de ciberseguridad. ¿En qué puedo ayudarte?</p>
                  </div>
                )}
                {messages.map((msg, index) => {
           const isLastBotMessage = index === messages.length - 1 && msg.sender === "bot" && typingText;
           if (isLastBotMessage) return null;

  return (
    <div key={index} className={`message ${msg.sender}`}>
      <strong>{msg.sender === "user" ? "" : ""}</strong>
      <div className="markdown-content">
        <ReactMarkdown
          rehypePlugins={[rehypeRaw]}
          remarkPlugins={[remarkGfm]}
        >
          {Array.isArray(msg.text) ? msg.text.join("\n") : msg.text}
        </ReactMarkdown>
      </div>
    </div>
  );
})}
              </>
            )}
{typingText && (
  <div className="message bot">
    <div className="markdown-content">
      <ReactMarkdown rehypePlugins={[rehypeRaw]} remarkPlugins={[remarkGfm]}>
        {typingText}
      </ReactMarkdown>
    </div>
  </div>
)}            
        {loading && (
          <div className="message bot typing-indicator">
            <span>.</span><span>.</span><span>.</span>
          </div>
        )}
            <div ref={chatEndRef} />
          </div>

          {/* Formulario */}
          <div className={`Form_Comple ${isOpen ? "mover-form" : ""} ${formBajado ? "bajar-formulario" : ""}`}>
            {selectedSession && (
              <div style={{ color: "#888", padding: 8 }}>
                Estás viendo una conversación pasada. Haz clic en <FontAwesomeIcon icon={faMessage} /> para escribir una nueva.
              </div>
            )}
            <form onSubmit={handleSend} className="chat-form">
              <textarea
                ref={textareaRef}
                className="chat-textarea"
                name="message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="Escribe tu mensaje..."
                autoComplete="off"
                disabled={loading || !!selectedSession}
              ></textarea>
              {selectedFile && (
                <div className="file-preview">
                  📎 Archivo seleccionado: <strong>{fileName}</strong>
                </div>
              )}
              <div className="buttom_env">
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,image/*"
                  style={{ display: "none" }}
                  onChange={handleFileChange}
                  disabled={uploading || !!selectedSession}
                />
                <button
                  type="button"
                  className="boton_mas"
                  onClick={() => !selectedSession && fileInputRef.current?.click()}
                  disabled={uploading || !!selectedSession}
                >
                  {uploading ? <FontAwesomeIcon icon={faSpinner} spin /> : <FontAwesomeIcon icon={faPlus} size="lg" />}
                </button>
                
                <AudioQuestion />

                <button className="boton_enviar" 
                type="submit" 
                onClick={handleSendMessage}
                disabled={loading || uploading || !!selectedSession}>
                  <FontAwesomeIcon icon={faArrowUp} size="lg" />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <LoginModal isOpen={showLoginModal} onClose={() => setShowLoginModal(false)} />
    </div>
  );
}

export default Chat;
