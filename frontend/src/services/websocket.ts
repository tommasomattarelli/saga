import { useAuthStore } from "../stores/auth-store";

type MessageHandler = (data: Record<string, unknown>) => void;

export class GameWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private campaignId: string;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  constructor(campaignId: string) {
    this.campaignId = campaignId;
  }

  connect(): void {
    const token = useAuthStore.getState().accessToken;
    if (!token) return;

    this.intentionalClose = false;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    this.ws = new WebSocket(`${protocol}://${host}/api/ws/${this.campaignId}?token=${token}`);

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const type = data.type as string;
      const typeHandlers = this.handlers.get(type) || [];
      typeHandlers.forEach((handler) => handler(data));

      const allHandlers = this.handlers.get("*") || [];
      allHandlers.forEach((handler) => handler(data));
    };

    this.ws.onclose = () => {
      if (!this.intentionalClose) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };
  }

  on(type: string, handler: MessageHandler): () => void {
    const handlers = this.handlers.get(type) || [];
    handlers.push(handler);
    this.handlers.set(type, handlers);
    return () => {
      const idx = handlers.indexOf(handler);
      if (idx >= 0) handlers.splice(idx, 1);
    };
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}
