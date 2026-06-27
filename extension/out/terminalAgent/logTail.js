"use strict";
/**
 * AGENT NEO - Terminal Agent Orchestrator: Log-file tailer
 *
 * Incrementally tails a growing log file, emitting only newly appended text.
 * The content reader is injectable so the tailing/delta logic is unit-testable
 * without touching the real filesystem; `fileReader` wires it to fs for the
 * extension. Rotation/truncation is handled via computeTailDelta.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.LogFileTailer = void 0;
exports.fileReader = fileReader;
const fs = __importStar(require("fs"));
const terminalObserver_1 = require("./terminalObserver");
class LogFileTailer {
    constructor(read, onDelta) {
        this.read = read;
        this.onDelta = onDelta;
        this.lastLength = 0;
        this.timer = null;
    }
    /**
     * Read the source once and emit only the part appended since the last poll.
     * Read failures (file missing/locked) are swallowed so polling can recover
     * once the file appears.
     */
    poll() {
        let content;
        try {
            content = this.read();
        }
        catch {
            return;
        }
        const { delta, newLength } = (0, terminalObserver_1.computeTailDelta)(this.lastLength, content);
        this.lastLength = newLength;
        if (delta) {
            this.onDelta(delta);
        }
    }
    /** Begin polling on an interval. Idempotent. */
    start(intervalMs = 1000) {
        if (this.timer) {
            return;
        }
        this.poll();
        this.timer = setInterval(() => this.poll(), intervalMs);
    }
    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }
    isRunning() {
        return this.timer !== null;
    }
}
exports.LogFileTailer = LogFileTailer;
/** A ContentReader backed by the real filesystem. */
function fileReader(path) {
    return () => fs.readFileSync(path, 'utf8');
}
//# sourceMappingURL=logTail.js.map