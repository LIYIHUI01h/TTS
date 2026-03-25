export class SocketService {
    constructor(url) {
        this.url = url;
        this.socket = null;
        this.onMessageCallback = null;
        this.reconnectTimer = null; // 记录重连定时器
    }

    connect() {
        // 清除旧连接和重连任务
        this.clearSocket();

        console.log(`📡 WebSocket: 正在连接 ${this.url}...`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = () => {
            console.log("✅ WebSocket: 已连接到后端");
        };

        this.socket.onmessage = (event) => {
            if (this.onMessageCallback) {
                try {
                    const payload = JSON.parse(event.data);
                    // 增加解构安全判定
                    const { type, data } = payload || {};
                    if (type) {
                        this.onMessageCallback(type, data);
                    }
                } catch (e) {
                    console.warn("⚠️ WebSocket: 收到非JSON格式消息", event.data);
                }
            }
        };

        this.socket.onclose = () => {
            console.warn("❌ WebSocket: 连接断开");
            // 只有当没有被手动销毁时才重连
            this.reconnect();
        };

        this.socket.onerror = (err) => {
            console.error("❌ WebSocket: 发生错误", err);
        };
    }

    reconnect() {
        if (this.reconnectTimer) return; // 防止重复启动重连
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, 5000);
    }

    onMessage(callback) {
        this.onMessageCallback = callback;
    }

    // 抽离出的清理方法
    clearSocket() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.socket) {
            this.socket.onopen = null;
            this.socket.onmessage = null;
            this.socket.onclose = null;
            this.socket.onerror = null;
            this.socket.close();
            this.socket = null;
        }
    }

    destroy() {
        console.log("🔌 WebSocket: 正在手动销毁连接...");
        this.onMessageCallback = null;
        this.clearSocket();
    }
}