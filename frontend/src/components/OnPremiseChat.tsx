import React, { useState, useEffect, useRef, FormEvent } from "react";
import { useOnPremiseChat } from "../hooks/useOnPremiseChat";
import { useChatVisibility } from "../hooks/useChatVisibility";
import LoginModal from "./LoginModal";
import ReactMarkdown from "react-markdown";
import AudioQuestion from "./AudioQuestion";
import { useConversationHistory } from "../hooks/useConversationHistory";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm"; 
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUp,
  faMagnifyingGlass,
  faMessage,
  faSun,
  faPlus,
  faSpinner,
  faCircleHalfStroke,
  faMicrophone,
} from "@fortawesome/free-solid-svg-icons";
import { useNavigate } from "react-router-dom";

function OnPremiseChat() {

  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const { history: sessionList, loading: loadingSessions } = useConversationHistory("openai", null, 15);
  const { history: sessionHistory, loading: loadingSessionHistory } = useConversationHistory("openai", selectedSession, 50);


  const { messages, sendMessage, loading } = useOnPremiseChat();
  const [formBajado, setFormBajado] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [displayedText, setDisplayedText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const navigate = useNavigate();
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
    if (!message.trim()) return;
    sendMessage(message.trim());
    setMessage(""); // Limpia el textarea
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    if (!formBajado) setFormBajado(true);
  };

  const handleInputResize = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  };

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.sender === "bot") {
      const fullText = Array.isArray(lastMsg.text)
        ? lastMsg.text.join("\n")
        : lastMsg.text;
      if (!fullText) return;

      let index = 0;
      setDisplayedText("");

      const interval = setInterval(() => {
        index++;
        setDisplayedText(fullText.slice(0, index));
        if (index >= fullText.length) clearInterval(interval);
      }, 15);

      return () => clearInterval(interval);
    }
  }, [messages]);

  const handleSend = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("message") as HTMLTextAreaElement;
    const message = input?.value.trim();

    if (!message && !selectedFile) return;

    if (message) {
      sendMessage(message);
    }

    if (selectedFile) {
      setUploading(true);
      const formData = new FormData();
      formData.append("file", selectedFile);

      sendMessage(`Analizando archivo "${selectedFile.name}"...`);

      try {
        const res = await fetch("http://127.0.0.1:8000/file/analyze", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        if (data.success) {
          sendMessage(`**Resumen de "${selectedFile.name}":**\n\n${data.summary || "No se obtuvo resumen."}`);
        } else {
          sendMessage(`No se pudo analizar el archivo "${selectedFile.name}".\n${data.error || ""}`);
        }
      } catch (err) {
        sendMessage("Error al subir o analizar el archivo.");
      }

      setUploading(false);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }

    input.value = "";
    setDisplayedText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    if (!formBajado) setFormBajado(true);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const toggleMenu = () => setMenuOpen((prev) => !prev);

  return (
    <div className="Chat_bot">
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
                         ¡Welcome Cloud!
                  </button>
      </div>
                    </div>
                    <div className={`Chat-Logo ${isOpen ? "mover-derecha" : ""}`}>
        <div className="Menu_Desplegable">
                  <div className="Chat-Logo" onClick={toggleMenu}>
                    <img src="LogoN.png" alt="Logo" className="logo" />
                  </div>
          {menuOpen && (
            <div className="desplegable-Cloud">
              <button
                onClick={() => {
                  setMenuOpen(false);
                  setIsOpen(false);
                  navigate("/");
                }}
              >
                <div className="title_Mateo"><span>Mateo</span>v5</div>
              </button>
            </div>
          )}
          <div className="Boton_Inicio">
                 <button onClick={() => setShowLoginModal(true)}>
                    Login
                 </button>
               </div>
        </div>
      </div>
                  </nav>
                </header>
      {selectedSession && (
  <div className="historial-chat">
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
  </div>
)}
              
      <div className={`claude-chat-box ${isOpen ? "mover-chat" : ""}`} ref={chatContainerRef}>
        {messages.length === 0 && (
          <div className="Message_Mateo">
            <p>Hola, analista. Bienvenido a tus consultas On-Premise</p>
          </div>
        )}

        {messages.map((msg, index) => {
          const text = Array.isArray(msg.text) ? msg.text.join("\n") : msg.text;
          const isLastBotMsg = index === messages.length - 1 && msg.sender === "bot";

          return (
            <div key={index} className={`message ${msg.sender}`}>
              {msg.sender === "bot" ? (
                <ReactMarkdown
                  rehypePlugins={[rehypeRaw]}
                  remarkPlugins={[remarkGfm]} 
                >
                  {isLastBotMsg ? displayedText : text || ""}
                </ReactMarkdown>
              ) : (
                <p>{text}</p>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="message bot typing-indicator">
            <span>.</span><span>.</span><span>.</span>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className={`Form_Comple ${isOpen ? "mover-form" : ""} ${formBajado ? "bajar-formulario" : ""}`}>
        <form onSubmit={handleSend} className="chat-form">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            name="message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault(); // Previene salto de línea
            handleSendMessage();
              }
            }}
            placeholder="Escribe tu mensaje..."
            autoComplete="off"
            disabled={loading}
            onInput={handleInputResize}
          ></textarea>

          {selectedFile && (
            <div className="file-preview">
              <p>📎 Archivo seleccionado: <strong>{selectedFile.name}</strong></p>
            </div>
          )}

          <div className="buttom_env">
            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,image/*"
              style={{ display: "none" }}
              onChange={handleFileChange}
              disabled={uploading}
            />
            <button
              type="button"
              className="boton_mas"
              style={{ marginLeft: 1 }}
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <FontAwesomeIcon icon={faSpinner} spin />
              ) : (
                <FontAwesomeIcon icon={faPlus} size="lg" />
              )}
            </button>
            
             <AudioQuestion />
            
            <button className="boton_enviar" type="submit" disabled={loading || uploading}>
              <FontAwesomeIcon icon={faArrowUp} size="lg" />
            </button>
          </div>
        </form>
      </div>
    <LoginModal isOpen={showLoginModal} onClose={() => setShowLoginModal(false)} />
      </div>
  );
}

export default OnPremiseChat;
