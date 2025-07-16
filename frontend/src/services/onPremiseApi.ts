import axios from "axios";

const API_URL = import.meta.env.VITE_MISTRAL_ENDPOINT + "/chat/mistral";

export const sendOnPremiseMessage = async (message: string) => {
    try {
        console.log("Enviando a Mistral:", { message, role: "privileged" });
        const response = await axios.post(
          API_URL,
          { message, data_sources: [], context_days: 2,role: "privileged" }, 
          { headers: { "Content-Type": "application/json" } }
        );    

        console.log("Respuesta de la API:", response.data);
        
        if (!response.data || typeof response.data !== 'object') {
            throw new Error("La respuesta no es válida.");
        }

        return response.data.response || response.data.message || "El servidor no devolvió una respuesta válida.";

    } catch (error) {
        console.error("Error al enviar el mensaje:", error);
        return "Hubo un error al conectar con el servidor.";
    }
};
