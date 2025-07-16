import axios from 'axios';
const API_URL = import.meta.env.VITE_BACKEND_URL + '/chat/openai';


export const sendMessage = async (message: string) => {
  try {
    const response = await axios.post(
      API_URL,
      { message, role: "normal" }, // "privileged" si es para Mistral
      { headers: { "Content-Type": "application/json" } }
    );    
    // Validar que la respuesta tenga la estructura esperada
    console.log("Respuesta de la API:", response.data);
    const messageResponse = response.data?.response || response.data?.message;
    if (messageResponse) {
      return messageResponse;
    } else {
      console.warn("La respuesta de la API no contiene los campos esperados:", response.data);
      return "El servidor no devolvió una respuesta válida.";
    }
  } catch (error) {
    console.error('Error al send el menssage:', error);
    return 'Hubo un error al conectar con el servidor.';
  }
};
