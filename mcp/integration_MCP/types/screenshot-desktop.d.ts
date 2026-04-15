declare module 'screenshot-desktop' {
    interface ScreenshotOptions {
        format?: 'png' | 'jpg';
    }
    function screenshot(options?: ScreenshotOptions): Promise<Buffer>;
    export default screenshot;
}
