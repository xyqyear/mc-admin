#Requires -Version 7.3
param([Parameter(Mandatory)][string]$Payload)
$ErrorActionPreference = 'Stop'
$request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Payload)) | ConvertFrom-Json
$env:MC_ADMIN_BROWSER_FIXTURE = $request.fixture
$env:MC_ADMIN_WSL_DISTRO = $request.distribution
$env:MC_ADMIN_BROWSER_CLIENT_METADATA = $request.metadata
$env:BROWSER_OUTPUT_DIR = $request.output

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

public static class BrowserJob {
    [StructLayout(LayoutKind.Sequential)]
    struct Limits {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
        public ulong ReadOperations, WriteOperations, OtherOperations;
        public ulong ReadBytes, WriteBytes, OtherBytes;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Accounting {
        public long UserTime, KernelTime, PeriodUserTime, PeriodKernelTime;
        public uint Faults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(SafeFileHandle job, int kind, ref Limits limits, uint size);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(SafeFileHandle job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool TerminateJobObject(SafeFileHandle job, uint code);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool QueryInformationJobObject(SafeFileHandle job, int kind, out Accounting information, uint size, IntPtr length);

    public static int Run(string node, string directory, string[] arguments) {
        using var job = CreateJobObject(IntPtr.Zero, null);
        if (job.IsInvalid) throw new Win32Exception();
        var limits = new Limits { Flags = 0x2000 }; // Closing the owner kills its complete Windows process tree.
        if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Limits>())) throw new Win32Exception();
        var start = new ProcessStartInfo(node) {
            WorkingDirectory = directory, UseShellExecute = false,
            RedirectStandardInput = true, CreateNoWindow = true
        };
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        using var child = Process.Start(start);
        try {
            if (!AssignProcessToJobObject(job, child.Handle)) throw new Win32Exception();
            child.StandardInput.WriteLine("start");
            child.StandardInput.Flush();
            var exited = child.WaitForExitAsync();
            var disconnected = Task.Run(() => Console.In.ReadToEnd());
            var completed = Task.WhenAny(exited, disconnected).GetAwaiter().GetResult();
            int code = completed == exited ? child.ExitCode : 130;
            if (!TerminateJobObject(job, 130)) throw new Win32Exception();
            var deadline = Stopwatch.StartNew();
            while (true) {
                if (!QueryInformationJobObject(job, 1, out Accounting information, (uint)Marshal.SizeOf<Accounting>(), IntPtr.Zero)) throw new Win32Exception();
                if (information.ActiveProcesses == 0) break;
                if (deadline.Elapsed.TotalSeconds > 3) throw new Exception("Windows browser writers did not terminate");
                System.Threading.Thread.Sleep(20);
            }
            child.WaitForExit();
            return code;
        } finally {
            job.Dispose();
            if (!child.HasExited) { child.Kill(true); child.WaitForExit(); }
        }
    }
}
'@

$node = (Get-Command node.exe -ErrorAction Stop).Source
$commandArguments = @((Join-Path $request.directory 'scripts/wsl-browser.mjs')) + @($request.arguments)
exit [BrowserJob]::Run($node, $request.directory, [string[]]$commandArguments)
