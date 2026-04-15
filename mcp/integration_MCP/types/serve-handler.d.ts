declare module 'serve-handler' {
    import { IncomingMessage, ServerResponse } from 'http';
    interface Options {
        public?: string;
        headers?: Array<{ source: string; headers: Array<{ key: string; value: string }> }>;
    }
    function serveHandler(req: IncomingMessage, res: ServerResponse, options?: Options): Promise<void>;
    export default serveHandler;
}
