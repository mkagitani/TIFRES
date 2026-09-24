
using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Tifres.App.ViewModels;
namespace Tifres.App.Views;

// Physical fiber centers: X=0..9, Y=0..11, positive Y upwards.
public static class IfuCoordinates
{
    public static Point ToScreen(Point p, Size size, IfuDisplaySettings s) => new(
        (s.InvertX ? 9.5 - p.X : p.X + .5) * size.Width / 10,
        (s.InvertY ? p.Y + .5 : 11.5 - p.Y) * size.Height / 12);
    public static int? FiberAt(Point p, Size size, IfuDisplaySettings s)
    {
        if (size.Width <= 0 || size.Height <= 0 || p.X < 0 || p.Y < 0 || p.X >= size.Width || p.Y >= size.Height) return null;
        var x = (int)(p.X * 10 / size.Width); var y = (int)(p.Y * 12 / size.Height);
        return (s.InvertY ? y : 11-y) * 10 + (s.InvertX ? 9-x : x);
    }
    public static Point EllipsePoint(IfuDisplaySettings s, double phase)
    {
        var a = (s.Angle % 360) * Math.PI / 180;
        var x = s.Width / 2 * Math.Cos(phase); var y = s.Height / 2 * Math.Sin(phase);
        return new(s.CenterX + x*Math.Cos(a)-y*Math.Sin(a), s.CenterY+x*Math.Sin(a)+y*Math.Cos(a));
    }
}
public abstract class DisplayLayer : Control
{
    private IfuDisplayViewModel? _model;
    protected IfuDisplayViewModel? Model => DataContext as IfuDisplayViewModel;
    protected DisplayLayer() { ClipToBounds = true; DataContextChanged += (_, _) => Subscribe(); }
    private void Subscribe()
    {
        if (_model != null) _model.PropertyChanged -= Changed;
        _model = Model;
        if (_model != null) _model.PropertyChanged += Changed;
        InvalidateVisual();
    }
    protected virtual bool Relevant(string? name) => name is "Applied" or "Cube" or "IfuValues" or "SelectedFibers";
    private void Changed(object? sender, PropertyChangedEventArgs e) { if(Relevant(e.PropertyName)) InvalidateVisual(); }
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    { if (_model != null) _model.PropertyChanged -= Changed; base.OnDetachedFromVisualTree(e); }
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e) { base.OnAttachedToVisualTree(e); Subscribe(); }
    public static Color IntensityColor(double value, double min, double max)
    {
        if(!double.IsFinite(value))return Color.FromRgb(150,70,170);
        var t = value <= min ? 0 : value >= max ? 1 : (value/2-min/2)/(max/2-min/2);
        var v = (byte)Math.Round(255*t);
        return Color.FromRgb(v,v,v);
    }
}
public sealed class IfuImageLayer : DisplayLayer
{
    public override void Render(DrawingContext context)
    {
        if (Model is not { } vm) return;
        for (var id=0; id<120; id++)
        {
            var p = IfuCoordinates.ToScreen(new(id%10,id/10), Bounds.Size, vm.Applied);
            context.FillRectangle(new SolidColorBrush(vm.Cube == null || !vm.Cube.Active[id] ? Color.FromRgb(45,55,65) : IntensityColor(vm.IfuValues[id],vm.Applied.IfuMin,vm.Applied.IfuMax)),
                new Rect(p.X-Bounds.Width/20,p.Y-Bounds.Height/24,Bounds.Width/10,Bounds.Height/12));
        }
    }
}
public sealed class IfuOverlayLayer : DisplayLayer
{
    private int? _start; private bool _add;
    public void SelectAt(Point p) { if (Model is { } vm && IfuCoordinates.FiberAt(p,Bounds.Size,vm.Applied) is int id) vm.SelectFiber(id,false); }
    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e); if(Model is not {} vm || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)return;
        _start=IfuCoordinates.FiberAt(e.GetPosition(this),Bounds.Size,vm.Applied);_add=e.KeyModifiers.HasFlag(KeyModifiers.Control);
        if(_start is int id)vm.SelectFiber(id,_add);e.Pointer.Capture(this);e.Handled=true;
    }
    protected override void OnPointerMoved(PointerEventArgs e)
    {
        if(Model is not {} vm)return;
        var id=IfuCoordinates.FiberAt(e.GetPosition(this),Bounds.Size,vm.Applied);
        if(id is int f)vm.CursorText=$"Fiber {f} · X={f%10}, Y={f/10} · I={vm.IfuValues[f]:G7}";
        if(_start is int a && id is int b && a!=b)vm.SelectRectangle(a,b,_add);
    }
    protected override void OnPointerReleased(PointerReleasedEventArgs e){_start=null;e.Pointer.Capture(null);base.OnPointerReleased(e);}
    public override void Render(DrawingContext context)
    {
        context.FillRectangle(Brushes.Transparent, new Rect(Bounds.Size));
        if (Model is not { } vm) return;
        var s = vm.Applied;
        if (vm.Cube != null && s.EllipseEnabled)
        {
            var points = Enumerable.Range(0,129).Select(i => IfuCoordinates.ToScreen(IfuCoordinates.EllipsePoint(s,i*Math.PI/64),Bounds.Size,s)).ToArray();
            if (points.All(p => double.IsFinite(p.X) && double.IsFinite(p.Y)))
            {
                var geometry = new StreamGeometry();
                using (var path = geometry.Open()) { path.BeginFigure(points[0],false); foreach (var p in points.Skip(1)) path.LineTo(p); path.EndFigure(true); }
                context.DrawGeometry(null,new Pen(new SolidColorBrush(Color.Parse(s.Color)),1.2),geometry);
            }
        }
        foreach (var id in vm.SelectedFibers)
        {
            var p = IfuCoordinates.ToScreen(new(id%10,id/10),Bounds.Size,s);
            context.DrawRectangle(null,new Pen(Brushes.Cyan,1),new Rect(p.X-Bounds.Width/20,p.Y-Bounds.Height/24,Bounds.Width/10,Bounds.Height/12));
        }
    }
}
// The spectral bitmap is rebuilt only for a new cube, view range, or intensity range.
public sealed class SpectralImageLayer : DisplayLayer
{
    private Avalonia.Media.Imaging.WriteableBitmap? _bitmap;
    private object? _cubeKey; private double _min,_max,_left,_right; private int _width;
    private int? _start; private bool _add;
    public int BitmapBuilds {get;private set;}
    protected override bool Relevant(string? n)=>n is "Cube" or "Applied" or "ZoomMin" or "SelectedFibers";
    private int Fiber(Point p)=>Math.Clamp(119-(int)(p.Y/Bounds.Height*120),0,119);
    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        if(Model is not {} vm || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)return;
        _start=Fiber(e.GetPosition(this));_add=e.KeyModifiers.HasFlag(KeyModifiers.Control);
        vm.SelectFiber(_start.Value,_add);e.Pointer.Capture(this);e.Handled=true;
    }
    protected override void OnPointerMoved(PointerEventArgs e)
    {
        if(Model is not {Cube:{} cube} vm)return;
        var p=e.GetPosition(this);var f=Fiber(p);var i=cube.Nearest(vm.ZoomMin+p.X/Bounds.Width*(vm.ZoomMax-vm.ZoomMin));
        vm.CursorText=$"λ={cube.Wavelengths[i]:G9} {cube.Metadata.WavelengthUnit} · Fiber {f} · I={cube.Value(f,i):G7}"+(cube.Active[f]?"":" · inactive");
        if(_start is int a && a!=f)vm.SelectFiberRange(a,f,_add);
    }
    protected override void OnPointerReleased(PointerReleasedEventArgs e){_start=null;e.Pointer.Capture(null);base.OnPointerReleased(e);}
    protected override void OnPointerWheelChanged(PointerWheelEventArgs e)
    { if(Model is {} vm){if(e.KeyModifiers.HasFlag(KeyModifiers.Shift))vm.Pan(-e.Delta.Y*.1);else vm.Zoom(Math.Pow(.8,e.Delta.Y),Math.Clamp(e.GetPosition(this).X/Bounds.Width,0,1));e.Handled=true;} }
    public override void Render(DrawingContext context)
    {
        if(Model is not {Cube:{} cube} vm){_bitmap?.Dispose();_bitmap=null;_cubeKey=null;context.FillRectangle(Brushes.LightGray,new Rect(Bounds.Size));return;}
        int width=Math.Clamp((int)Math.Ceiling(Bounds.Width),1,4096);
        if(_bitmap==null || _cubeKey!=cube || _width!=width || _min!=vm.Applied.SpectralMin || _max!=vm.Applied.SpectralMax || _left!=vm.ZoomMin || _right!=vm.ZoomMax)
        {
            _bitmap?.Dispose();_bitmap=new(new PixelSize(width,120),new Vector(96,96),Avalonia.Platform.PixelFormat.Bgra8888,Avalonia.Platform.AlphaFormat.Opaque);
            using(var buffer=_bitmap.Lock())
            {
                var bytes=new byte[buffer.RowBytes*120];
                for(int row=0;row<120;row++)for(int x=0;x<width;x++)
                {
                    int f=119-row, i=cube.Nearest(vm.ZoomMin+(x+.5)/width*(vm.ZoomMax-vm.ZoomMin));
                    var c=cube.Active[f]?IntensityColor(cube.Value(f,i),vm.Applied.SpectralMin,vm.Applied.SpectralMax):Color.FromRgb(45,55,65);
                    int at=row*buffer.RowBytes+x*4;bytes[at]=c.B;bytes[at+1]=c.G;bytes[at+2]=c.R;bytes[at+3]=255;
                }
                System.Runtime.InteropServices.Marshal.Copy(bytes,0,buffer.Address,bytes.Length);
            }
            _cubeKey=cube;_width=width;_min=vm.Applied.SpectralMin;_max=vm.Applied.SpectralMax;_left=vm.ZoomMin;_right=vm.ZoomMax;BitmapBuilds++;
        }
        Avalonia.Media.RenderOptions.SetBitmapInterpolationMode(this,Avalonia.Media.Imaging.BitmapInterpolationMode.None);
        context.DrawImage(_bitmap,new Rect(_bitmap.Size),new Rect(Bounds.Size));
        foreach(var f in vm.SelectedFibers)context.DrawRectangle(null,new Pen(Brushes.Cyan,1),new Rect(0,(119-f)*Bounds.Height/120,Bounds.Width,Bounds.Height/120));
    }
    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e){_bitmap?.Dispose();_bitmap=null;_cubeKey=null;base.OnDetachedFromVisualTree(e);}
}
public sealed class SpectrumLayer : DisplayLayer
{
    protected override bool Relevant(string? n)=>n is "Cube" or "SpectrumValues" or "ZoomMin";
    private Point? _pan;
    protected override void OnPointerWheelChanged(PointerWheelEventArgs e)
    { if(Model is {} vm){if(e.KeyModifiers.HasFlag(KeyModifiers.Shift))vm.Pan(-e.Delta.Y*.1);else vm.Zoom(Math.Pow(.8,e.Delta.Y),Math.Clamp(e.GetPosition(this).X/Bounds.Width,0,1));e.Handled=true;} }
    protected override void OnPointerPressed(PointerPressedEventArgs e){_pan=e.GetPosition(this);e.Pointer.Capture(this);}
    protected override void OnPointerReleased(PointerReleasedEventArgs e){_pan=null;e.Pointer.Capture(null);}
    protected override void OnPointerMoved(PointerEventArgs e)
    {
        if(Model is not {Cube:{} cube} vm || vm.SpectrumValues.Count!=cube.Samples)return;var p=e.GetPosition(this);
        if(_pan is Point prev){vm.Pan((prev.X-p.X)/Bounds.Width);_pan=p;}
        int i=cube.Nearest(vm.ZoomMin+p.X/Bounds.Width*(vm.ZoomMax-vm.ZoomMin));
        vm.CursorText=$"λ={cube.Wavelengths[i]:G9} {cube.Metadata.WavelengthUnit} · I={vm.SpectrumValues[i]:G7} · {vm.SelectionText}";
    }
    public override void Render(DrawingContext context)
    {
        context.FillRectangle(Brushes.White,new Rect(Bounds.Size));
        if(Model is not {Cube:{} cube} vm || vm.SpectrumValues.Count!=cube.Samples)return;
        var range=vm.SpectrumRange;Point? previous=null;
        // Draw only the visible samples; nonfinite values break the line.
        int first=Math.Max(0,cube.Nearest(vm.ZoomMin)-1),last=Math.Min(cube.Samples-1,cube.Nearest(vm.ZoomMax)+1);
        var pen=new Pen(Brushes.DarkBlue,1);
        var stride=Math.Max(1,(last-first+1)/Math.Max(1,(int)Bounds.Width*2));
        for(var i=first;i<=last;i+=stride)
        {
            if(stride>1)
            {
                double low=double.PositiveInfinity,high=double.NegativeInfinity;
                for(int j=i;j<=Math.Min(last,i+stride-1);j++){var v=vm.SpectrumValues[j];if(double.IsFinite(v)){low=Math.Min(low,v);high=Math.Max(high,v);}}
                if(double.IsFinite(low))
                {
                    var x=(cube.Wavelengths[i]-vm.ZoomMin)/(vm.ZoomMax-vm.ZoomMin)*Bounds.Width;
                    context.DrawLine(pen,new Point(x,(range.Max-low)/(range.Max-range.Min)*Bounds.Height),new Point(x,(range.Max-high)/(range.Max-range.Min)*Bounds.Height));
                }
                continue; // Display-only min/max envelope keeps narrow peaks visible.
            }
            var value=vm.SpectrumValues[i];if(!double.IsFinite(value)){previous=null;continue;}
            var p=new Point((cube.Wavelengths[i]-vm.ZoomMin)/(vm.ZoomMax-vm.ZoomMin)*Bounds.Width,
                (range.Max-value)/(range.Max-range.Min)*Bounds.Height);
            if(previous is Point q)context.DrawLine(pen,q,p);
            previous=p;
        }
    }
}
