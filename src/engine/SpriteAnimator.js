export class SpriteAnimator {
    manifest;
    action = 'idle';
    framePosition = 0;
    elapsed = 0;
    playing = true;
    fallback = false;
    constructor(manifest) {
        this.manifest = manifest;
        this.resolveAction('idle');
    }
    setManifest(manifest) {
        this.manifest = manifest;
        this.resolveAction(this.action);
    }
    dispatch(event) {
        const requested = event.action;
        const definition = this.manifest.actions[requested];
        const current = this.manifest.actions[this.action];
        if (!definition && current && current.interruptible === false) {
            return;
        }
        this.resolveAction(requested);
        this.playing = true;
    }
    tick(deltaMs) {
        if (!this.playing)
            return;
        const definition = this.manifest.actions[this.action];
        if (!definition || definition.frameIndices.length <= 1)
            return;
        this.elapsed += deltaMs;
        const frameDuration = 1000 / Math.max(1, definition.fps);
        while (this.elapsed >= frameDuration) {
            this.elapsed -= frameDuration;
            if (this.framePosition < definition.frameIndices.length - 1) {
                this.framePosition += 1;
            }
            else if (definition.loop) {
                this.framePosition = 0;
            }
            else {
                this.playing = false;
            }
        }
    }
    pause() {
        this.playing = false;
    }
    resume() {
        this.playing = true;
    }
    reset() {
        this.resolveAction('idle');
        this.playing = true;
    }
    snapshot() {
        const definition = this.manifest.actions[this.action];
        return {
            action: this.action,
            frameIndex: definition?.frameIndices[this.framePosition] ?? 0,
            framePosition: this.framePosition,
            isPlaying: this.playing,
            usingFallback: this.fallback,
        };
    }
    resolveAction(requested) {
        const definition = this.manifest.actions[requested];
        if (definition && definition.frameIndices.length > 0) {
            this.action = requested;
            this.fallback = false;
        }
        else {
            this.action = 'idle';
            this.fallback = requested !== 'idle';
        }
        this.framePosition = 0;
        this.elapsed = 0;
    }
}
