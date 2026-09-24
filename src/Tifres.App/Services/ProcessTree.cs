using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Tifres.App.Services;

// Own descendants even when the immediate Python parent exits before its children.
internal sealed class ProcessTree : IDisposable
{
    private SafeFileHandle? _job;
    private int _processGroup;

    public static void Prepare(ProcessStartInfo start)
    {
        if (!OperatingSystem.IsLinux()) return;
        var setsid = new[] { "/usr/bin/setsid", "/bin/setsid" }.FirstOrDefault(File.Exists)
            ?? throw new FileNotFoundException("Linux process isolation requires setsid (util-linux).");
        start.ArgumentList.Insert(0, start.FileName);
        start.ArgumentList.Insert(0, "--");
        start.FileName = setsid;
    }

    public void Attach(Process process)
    {
        if (OperatingSystem.IsLinux()) { _processGroup = process.Id; return; }
        if (!OperatingSystem.IsWindows()) return;
        _job = CreateJobObject(IntPtr.Zero, null);
        if (_job.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        var limits = new ExtendedLimitInformation();
        limits.Basic.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(_job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimitInformation>()))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        if (!AssignProcessToJobObject(_job, process.Handle) && !process.HasExited)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to contain Python in a Windows Job Object.");
    }

    public void Terminate(Process process)
    {
        // On Windows verify the .NET tree-kill path, then also kill the Job to cover
        // descendants reparented after an early parent exit. Called only on a worker.
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
        finally
        {
            if (_job is { IsInvalid: false, IsClosed: false } && !TerminateJobObject(_job, 1))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            if (_processGroup > 0)
            {
                var result = kill(-_processGroup, 9);
                if (result != 0 && Marshal.GetLastWin32Error() != 3) // ESRCH: already exited
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        }
    }

    public void Dispose()
    {
        _job?.Dispose();
        if (_processGroup > 0) kill(-_processGroup, 9);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation
    {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters { public ulong ReadOperation, WriteOperation, OtherOperation, ReadTransfer, WriteTransfer, OtherTransfer; }
    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation
    {
        public BasicLimitInformation Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateJobObject(IntPtr attributes, string? name);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetInformationJobObject(SafeFileHandle job, int type, ref ExtendedLimitInformation data, uint length);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AssignProcessToJobObject(SafeFileHandle job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool TerminateJobObject(SafeFileHandle job, uint exitCode);
    [DllImport("libc", SetLastError = true)]
    private static extern int kill(int pid, int signal);
}
