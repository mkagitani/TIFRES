using System.Text;

namespace Tifres.App.Services;

// A bounded text display, independent of transport chunk boundaries. CR returns
// to column zero; LF ends the line. This is not a full ANSI terminal emulator.
public sealed class ConsoleLogBuffer
{
    private readonly StringBuilder _text = new();
    private int _cursor, _lineStart;
    private bool _truncated;
    public string Text => (_truncated ? "[Earlier log truncated]\n" : "") + _text;

    public void Clear() { _text.Clear(); _cursor = _lineStart = 0; _truncated = false; }

    public void Append(string characters)
    {
        foreach (var character in characters)
        {
            if (character == '\r') _cursor = _lineStart;
            else if (character == '\n')
            {
                _text.Append('\n'); _cursor = _lineStart = _text.Length;
            }
            else
            {
                if (_cursor < _text.Length) _text[_cursor] = character;
                else _text.Append(character);
                _cursor++;
            }
            if (_text.Length > 20_000)
            {
                var remove = _text.Length - 16_000;
                _text.Remove(0, remove);
                _cursor = Math.Max(0, _cursor - remove);
                _lineStart = Math.Max(0, _lineStart - remove);
                _truncated = true;
            }
        }
    }

    public void AppendMessage(string message)
    {
        if (_text.Length != 0 && _text[^1] != '\n') Append("\n");
        Append(message); Append("\n");
    }
}
