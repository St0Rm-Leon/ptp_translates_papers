using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            Console.OutputEncoding = new UTF8Encoding(false);
        }
        catch (Exception)
        {
            // No console (for example when launched by a service); continue.
        }

        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        string python = Path.Combine(root, "runtime", "ptp", "python.exe");

        try
        {
            Directory.SetCurrentDirectory(root);
            Console.Title = "PTP Translates Papers";
        }
        catch (Exception)
        {
            // Non-fatal for CLI use.
        }

        if (!File.Exists(python))
        {
            Console.Error.WriteLine("PTP runtime not found: " + python);
            Console.Error.WriteLine("Extract the full portable package before running ptp.exe.");
            PauseIfDoubleClicked(args);
            return 1;
        }

        ProcessStartInfo startInfo = new ProcessStartInfo
        {
            FileName = python,
            Arguments = "-m ptp " + JoinArguments(args),
            WorkingDirectory = root,
            UseShellExecute = false,
        };
        startInfo.EnvironmentVariables["PYTHONUTF8"] = "1";
        startInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        startInfo.EnvironmentVariables["MINERU_HOME"] = Path.Combine(root, "data", "mineru-home");
        startInfo.EnvironmentVariables["HF_HOME"] = Path.Combine(root, "data", "hf-cache");

        try
        {
            using (Process process = Process.Start(startInfo))
            {
                if (process == null)
                {
                    Console.Error.WriteLine("Could not start the PTP runtime.");
                    PauseIfDoubleClicked(args);
                    return 1;
                }
                process.WaitForExit();
                int exitCode = process.ExitCode;
                if (args.Length == 0 && exitCode != 0)
                {
                    PauseIfDoubleClicked(args);
                }
                return exitCode;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Failed to start PTP: " + ex.Message);
            PauseIfDoubleClicked(args);
            return 1;
        }
    }

    private static void PauseIfDoubleClicked(string[] args)
    {
        if (args.Length != 0 || !Environment.UserInteractive)
        {
            return;
        }
        Console.WriteLine();
        Console.WriteLine("Press Enter to close...");
        try
        {
            Console.ReadLine();
        }
        catch (Exception)
        {
            // Ignore redirected input.
        }
    }

    private static string JoinArguments(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return string.Empty;
        }
        string[] quoted = new string[args.Length];
        for (int i = 0; i < args.Length; i++)
        {
            quoted[i] = Quote(args[i]);
        }
        return string.Join(" ", quoted);
    }

    private static string Quote(string value)
    {
        if (value.Length == 0)
        {
            return "\"\"";
        }
        if (value.IndexOfAny(new char[] { ' ', '\t', '"', '\\' }) < 0)
        {
            return value;
        }

        StringBuilder builder = new StringBuilder();
        builder.Append('"');
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                builder.Append(character);
            }
            else if (character == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
            }
            else
            {
                builder.Append(character);
                backslashes = 0;
            }
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }
}
