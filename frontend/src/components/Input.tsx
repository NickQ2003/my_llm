import React from "react";
type InputProps = {
    onSend: (message: string) => void;
  };
  
  const Input = ({ onSend }: InputProps) => {
    const [text, setText] = React.useState("");
  
    const handleSend = () => {
      if (text.trim()) {
        onSend(text);
        setText("");
      }
    };
  
    return (
      <div className="input-container">
        <input
          className="input-field"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Escribe tu mensaje..."
        />
        <button
          className="input-send-btn"
          onClick={handleSend}
        >
          Enviar
        </button>
      </div>
    );
  };
  
  export default Input;

 