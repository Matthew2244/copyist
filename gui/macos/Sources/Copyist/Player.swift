import AVFoundation
import Foundation

/// A/B audition — DESIGN.md 16.
///
/// The feature this app most needed and the reason it exists in this shape:
/// you cannot proofread a page you cannot see, but you can absolutely hear
/// whether the notated version still sounds like what you meant. So Copyist
/// plays two things:
///
///   original   the MIDI you exported from the DAW
///   notated    what the SCORE says — quantized onsets, notated durations,
///              the articulations Copyist chose
///
/// If those disagree in a way you can hear, Copyist got something wrong, and
/// that is a far better bug report than anything a rendered page could give.
final class Player: ObservableObject {

    @Published private(set) var playing: String?     // "original" / "notated"

    private var player: AVMIDIPlayer?
    private var onFinish: (() -> Void)?

    /// macOS ships a General MIDI sound bank; without it AVMIDIPlayer is silent.
    private static let soundBank: URL? = {
        let p = "/System/Library/Components/CoreAudio.component/Contents/"
              + "Resources/gs_instruments.dls"
        return FileManager.default.isReadableFile(atPath: p)
            ? URL(fileURLWithPath: p) : nil
    }()

    var available: Bool { Player.soundBank != nil }

    func play(_ url: URL, label: String, whenDone: (() -> Void)? = nil) throws {
        stop()
        let p = try AVMIDIPlayer(contentsOf: url, soundBankURL: Player.soundBank)
        p.prepareToPlay()
        player = p
        onFinish = whenDone
        playing = label
        p.play { [weak self] in
            DispatchQueue.main.async {
                self?.playing = nil
                self?.onFinish?()
                self?.onFinish = nil
            }
        }
    }

    func stop() {
        player?.stop()
        player = nil
        onFinish = nil
        playing = nil
    }

    var duration: TimeInterval { player?.duration ?? 0 }
}
