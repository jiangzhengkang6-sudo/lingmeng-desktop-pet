import { describe, expect, it } from 'vitest';
import { SpriteAnimator } from './SpriteAnimator';
function createManifest() {
    return {
        name: 'test-pet',
        version: '0.1.0',
        canvas: { width: 520, height: 520, background: 'transparent' },
        actions: {
            idle: {
                id: 'idle',
                label: '待机',
                frameIndices: [0, 1, 2],
                fps: 10,
                loop: true,
                interruptible: true,
            },
            success: {
                id: 'success',
                label: '成功',
                frameIndices: [3, 4],
                fps: 10,
                loop: false,
                interruptible: true,
            },
        },
    };
}
describe('SpriteAnimator', () => {
    it('advances frames at the action frame rate', () => {
        const animator = new SpriteAnimator(createManifest());
        animator.tick(100);
        expect(animator.snapshot()).toMatchObject({ action: 'idle', frameIndex: 1, framePosition: 1 });
    });
    it('stops on the final frame of a non-looping action', () => {
        const animator = new SpriteAnimator(createManifest());
        animator.dispatch({ action: 'success' });
        animator.tick(200);
        expect(animator.snapshot()).toMatchObject({
            action: 'success',
            frameIndex: 4,
            framePosition: 1,
            isPlaying: false,
        });
    });
    it('falls back to idle when an action resource is unavailable', () => {
        const animator = new SpriteAnimator(createManifest());
        animator.dispatch({ action: 'working' });
        expect(animator.snapshot()).toMatchObject({ action: 'idle', usingFallback: true });
    });
});
