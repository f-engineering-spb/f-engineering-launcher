# Modern Windows system folder dialog for FLauncher.
# Same dialog as File Explorer: IFileOpenDialog with FOS_PICKFOLDERS.
# No custom windows: one call, one standard dialog.
# Force UTF-8 on stdout so Cyrillic paths survive the pipe to Python.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class ModernFolderPicker
{
    private const uint FOS_PICKFOLDERS = 0x20;
    private const uint FOS_FORCEFILESYSTEM = 0x40;
    private const uint SIGDN_FILESYSPATH = 0x80058000;

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [ComImport]
    [Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    private class DialogRCW { }

    [ComImport]
    [Guid("D57C7288-D4AD-4768-BE02-9D969532D960")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileOpenDialog
    {
        [PreserveSig] int Show(IntPtr parent);
        void Slot02(); void Slot03(); void Slot04(); void Slot05(); void Slot06();
        void SetOptions(uint fos);
        void GetOptions(out uint fos);
        void Slot09(); void Slot10(); void Slot11(); void Slot12();
        void Slot13(); void Slot14();
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void Slot16(); void Slot17();
        void GetResult(out IShellItem item);
        void Slot19(); void Slot20(); void Slot21(); void Slot22(); void Slot23(); void Slot24();
        void Slot25(); void Slot26();
    }

    [ComImport]
    [Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void Slot01(); void Slot02();
        [PreserveSig] int GetDisplayName(uint sigdnName, out IntPtr ppszName);
    }

    public static string PickFolder(string title)
    {
        var dlg = (IFileOpenDialog)new DialogRCW();
        dlg.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        dlg.SetTitle(title);
        IntPtr parent = GetForegroundWindow();
        if (dlg.Show(parent) != 0) return null;
        IShellItem item;
        dlg.GetResult(out item);
        IntPtr ptr;
        if (item.GetDisplayName(SIGDN_FILESYSPATH, out ptr) != 0) return null;
        string path = Marshal.PtrToStringUni(ptr);
        Marshal.FreeCoTaskMem(ptr);
        return path;
    }
}
"@

$path = [ModernFolderPicker]::PickFolder("Select object folder - FLauncher")
if ($path) {
    [Console]::WriteLine($path)
}
