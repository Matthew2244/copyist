using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using Microsoft.Win32;

namespace Copyist;

public sealed record Row(string Label, string Value, string Extra = "")
{
    /// One utterance for a screen reader, rather than three stops.
    public string Spoken => $"{Label}. {Value}. {Extra}".Trim();
}

public sealed record FindingGroup(string Title, List<Finding> Items);

public partial class MainWindow : Window
{
    private string? _midiPath;
    private Analysis? _analysis;
    private Conversion? _conversion;

    public MainWindow()
    {
        InitializeComponent();
        foreach (var i in Enumerable.Range(8, 17)) ReachBox.Items.Add(i);
        foreach (var i in Enumerable.Range(6, 19)) ComfortBox.Items.Add(i);
        ReachBox.SelectedItem = 17;      // an eleventh
        ComfortBox.SelectedItem = 14;
    }

    /// Speak without moving focus. The status TextBlock is a live region, so
    /// setting its text is what actually announces; this also raises the
    /// automation event for clients that want it explicitly.
    private void Announce(string message)
    {
        StatusText.Text = message;
        if (AutomationPeer.ListenerExists(AutomationEvents.LiveRegionChanged))
        {
            var peer = UIElementAutomationPeer.FromElement(StatusText)
                       ?? UIElementAutomationPeer.CreatePeerForElement(StatusText);
            peer?.RaiseAutomationEvent(AutomationEvents.LiveRegionChanged);
        }
    }

    private void ShowError(string message)
    {
        MessageBox.Show(this, message, "Copyist could not do that",
                        MessageBoxButton.OK, MessageBoxImage.Warning);
    }

    private async void OnOpen(object sender, RoutedEventArgs e)
    {
        var dlg = new OpenFileDialog
        {
            Title = "Choose a MIDI file exported from your DAW",
            Filter = "MIDI files (*.mid;*.midi)|*.mid;*.midi|All files (*.*)|*.*",
        };
        if (dlg.ShowDialog(this) != true) return;

        _midiPath = dlg.FileName;
        _conversion = null;
        ResultPanel.Visibility = Visibility.Collapsed;
        ConvertButton.IsEnabled = false;
        Announce($"Analyzing {Path.GetFileName(_midiPath)}…");

        try
        {
            var a = await Task.Run(() => Engine.Analyze(_midiPath!));
            _analysis = a;
            PopulateAnalysis(a);
            ConvertButton.IsEnabled = true;
            Announce("Analysis finished. " + a.Headline);
        }
        catch (Exception ex)
        {
            _analysis = null;
            AnalysisPanel.Visibility = Visibility.Collapsed;
            SettingsPanel.Visibility = Visibility.Collapsed;
            Announce("Could not read that file.");
            ShowError(ex.Message);
        }
    }

    private void PopulateAnalysis(Analysis a)
    {
        WelcomeText.Visibility = Visibility.Collapsed;
        WelcomeBody.Visibility = Visibility.Collapsed;

        var rows = new List<Row>
        {
            new("Timing", a.TimingExplanation,
                $"Grid {a.Grid}, {a.OnGrid:F1}% of notes exactly on it"),
            new("Note lengths", a.LengthsQuantized
                ? "Quantized. No phantom rests to remove."
                : $"Not quantized — median release {a.LengthMedianMs:F1} milliseconds early. "
                  + "This is what makes stray rests."),
            new("Tempo and meter",
                $"{Math.Round(a.Bpm)} BPM{(a.ConstantTempo ? ", constant" : ", variable")}, {a.Meter}"),
        };

        if (a.Keys.Count > 0)
        {
            var top = a.Keys[0];
            var second = a.Keys.Count > 1 ? a.Keys[1] : null;
            rows.Add(new Row("Key",
                second is null
                    ? $"{top.Name} at {top.Confidence}%"
                    : $"{top.Name} at {top.Confidence}%, or {second.Name} at {second.Confidence}%",
                second is not null && second.Confidence >= 40
                    ? "Close enough to be worth choosing yourself." : ""));
        }

        rows.Add(new Row("Texture",
            $"Up to {a.MaxSimultaneous} notes at once, widest {a.WidestName}"));
        rows.Add(new Row("Velocity", $"{a.VelocityLow} to {a.VelocityHigh}"));
        rows.Add(new Row("Sustain pedal", a.Pedal > 0
            ? $"{a.Pedal} depressions, which become pedal marks"
            : "None in the file"));
        rows.Add(new Row("Markers", a.Markers > 0
            ? $"{a.Markers} found"
            : "None. In REAPER, project markers survive MIDI export; regions and take markers do not."));
        if (a.TrackNames.Count > 0)
            rows.Add(new Row("Tracks", string.Join("; ", a.TrackNames)));

        AnalysisRows.ItemsSource = rows;
        AnalysisPanel.Visibility = Visibility.Visible;

        KeyBox.Items.Clear();
        KeyBox.Items.Add(new KeyGuess("Let Copyist decide", 0));
        foreach (var k in a.Keys) KeyBox.Items.Add(k);
        KeyBox.SelectedIndex = 0;
        SettingsPanel.Visibility = Visibility.Visible;
    }

    private async void OnConvert(object sender, RoutedEventArgs e)
    {
        if (_midiPath is null) return;
        var outPath = Path.ChangeExtension(_midiPath, ".musicxml");
        var key = (KeyBox.SelectedItem as KeyGuess) is { Confidence: > 0 } g
            ? g.Name : null;
        var reach = ReachBox.SelectedItem as int? ?? 17;
        var comfort = ComfortBox.SelectedItem as int? ?? 14;

        ConvertButton.IsEnabled = false;
        Announce("Converting…");
        try
        {
            var c = await Task.Run(() =>
                Engine.Convert(_midiPath!, outPath, key, reach, comfort));
            _conversion = c;
            PopulateResult(c);
            Announce("Conversion finished. " + c.Headline
                     + $" Saved as {Path.GetFileName(c.Output)}.");
        }
        catch (Exception ex)
        {
            Announce("Conversion failed.");
            ShowError(ex.Message);
        }
        finally { ConvertButton.IsEnabled = true; }
    }

    private void PopulateResult(Conversion c)
    {
        var low = c.Int("handsLowConfidence");
        ResultRows.ItemsSource = new List<Row>
        {
            new("Saved", Path.GetFileName(c.Output), c.Output),
            new("Score", $"{c.Int("measures")} bars of {c.Instrument} in {c.Key}"),
            new("Phantom rests removed", c.Int("phantomRestsRemoved").ToString(),
                $"{c.Int("genuineRests")} genuine rests kept"),
            new("Hands",
                $"{c.Int("handsCertain")} certain, {c.Int("handsInferred")} inferred",
                low > 0 ? $"{low} low confidence — listen to those and lock them"
                        : "None low confidence."),
        };

        var titles = new (string Key, string Title)[]
        {
            ("will-look-bad", "Will look bad — needs your judgement"),
            ("uncertain", "Unsure — Copyist guessed"),
            ("fixed-silently", "Fixed for you"),
        };
        FindingGroups.ItemsSource = titles
            .Select(t => new FindingGroup(
                $"{t.Title} ({c.Findings.Count(f => f.Severity == t.Key)})",
                c.Findings.Where(f => f.Severity == t.Key).ToList()))
            .Where(g => g.Items.Count > 0)
            .ToList();

        ResultPanel.Visibility = Visibility.Visible;
    }

    private void OnReveal(object sender, RoutedEventArgs e)
    {
        if (_conversion is null) return;
        Process.Start(new ProcessStartInfo("explorer.exe",
            $"/select,\"{_conversion.Output}\"") { UseShellExecute = true });
    }
}
