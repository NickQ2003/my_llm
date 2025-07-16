import React, { useRef, useState } from "react";
import "../styles/AudioQuestion.css";
import { faMicrophone, faStop } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
 
const AudioQuestion: React.FC = () => {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string>("");
  const [llmResponse, setLlmResponse] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const audioChunks = useRef<Blob[]>([]);
 
  const startRecording = async () => {
    setTranscript("");
    setLlmResponse("");
    setAudioUrl(null);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    audioChunks.current = [];
 
    mediaRecorder.ondataavailable = (e: BlobEvent) => {
      if (e.data.size > 0) {
        audioChunks.current.push(e.data);
      }
    };
    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks.current, { type: "audio/wav" });
      setAudioUrl(URL.createObjectURL(audioBlob));
      sendAudio(audioBlob);
      stream.getTracks().forEach(track => track.stop());
    };
    mediaRecorder.start();
    setIsRecording(true);
  };
 
  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };
 
  const sendAudio = async (audioBlob: Blob) => {
    setLoading(true);
    const formData = new FormData();
    formData.append("audio", audioBlob, "pregunta.wav");
 
    try {
      const response = await fetch("/audio/question", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      setTranscript(data.transcript || "");
      setLlmResponse(data.llm_response || "");
    } catch (err) {
      setTranscript("Error procesando el audio.");
      setLlmResponse("");
    }
    setLoading(false);
  };
 
  return (
<div className="audio-question-container">
<h2 className="audio-title">Pregunta por voz</h2>
<div className="audio-controls">
<button
          className={`audio-btn ${isRecording ? "btn-stop" : "btn-record"}`}
          onClick={isRecording ? stopRecording : startRecording}
>
          {isRecording ? <FontAwesomeIcon icon={faStop} style={{ color: "red" }} />: <FontAwesomeIcon icon={faMicrophone} style={{ color: "#ffffff" }}  />


}
</button>
        {isRecording && <span className="audio-recording-label">Grabando...</span>}
</div>
      {audioUrl && (
<audio src={audioUrl} controls className="audio-player" />
      )}
      {loading && (
<div className="audio-loading">Procesando audio…</div>
      )}
      {transcript && (
<div className="audio-section">
<strong>Transcripción:</strong>
<div className="audio-transcript">{transcript}</div>
</div>
      )}
      {llmResponse && (
<div className="audio-section">
<strong>Respuesta:</strong>
<div className="audio-response">{llmResponse}</div>
</div>
      )}
</div>
  );
};
 
export default AudioQuestion;