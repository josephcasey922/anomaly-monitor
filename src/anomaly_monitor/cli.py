"""Command line entry points for local demo, config runs, and polling."""
from __future__ import annotations
from pathlib import Path
import argparse,os,sys,time
import yaml
from .pipeline import run_pipeline
from .demo import generate_wide_demo
from .config import load_config


def main(argv:list[str]|None=None):
    parser=argparse.ArgumentParser(prog="anomaly-monitor",description="CSV/PostgreSQL statistical anomaly screening")
    sub=parser.add_subparsers(dest="command",required=True)
    app=sub.add_parser("app",help="Launch local Streamlit import wizard")
    demo=sub.add_parser("demo",help="Generate synthetic wide CSV + configuration and run")
    demo.add_argument("--directory",type=Path,default=Path("my-monitor-demo"))
    run=sub.add_parser("run",help="Run a CSV or PostgreSQL YAML profile once")
    run.add_argument("--config",type=Path,required=True)
    watch=sub.add_parser("watch",help="Poll source and rerun reports (not sub-second streaming)")
    watch.add_argument("--config",type=Path,required=True)
    watch.add_argument("--interval",type=float,default=60.)
    args=parser.parse_args(argv)
    if args.command=="app":
        import subprocess
        app_file=Path(__file__).with_name("app.py")
        sys.exit(subprocess.call([sys.executable,"-m","streamlit","run",str(app_file),
                                  "--server.address","127.0.0.1","--browser.gatherUsageStats","false"]))
    if args.command=="demo":
        target=args.directory.resolve()
        target.mkdir(parents=True,exist_ok=True)
        from importlib.resources import files
        source=files("anomaly_monitor").joinpath("templates/config.yaml")
        cfg=yaml.safe_load(source.read_text(encoding="utf-8"))
        cfg["input"].update({"source":"csv","path":"demo_wide.csv","frequency":"D"})
        cfg["output"]["directory"]="outputs"
        path=target/"config.yaml"
        csv=target/"demo_wide.csv"
        if path.exists() or csv.exists():
            parser.error("Demo refuses to overwrite existing data/config")
        path.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
        frame=generate_wide_demo()
        frame.to_csv(csv,index=False)
        print(f"Created {csv} ({len(frame):,} store-days) and {path}")
        outputs=run_pipeline(path)
        for key,value in outputs.items():print(f"{key}: {value}")
    elif args.command=="run":
        result=run_pipeline(args.config)
        for key,path in result.items():print(f"{key}: {path}")
    elif args.command=="watch":
        if args.interval<10:parser.error("--interval must be >=10 seconds")
        cfg=load_config(args.config)
        source=cfg["input"].get("source","csv")
        path=cfg["input"].get("path")
        previous=None
        print(f"Polling {source} every {args.interval}s. Press Ctrl+C to stop.",flush=True)
        try:
            while True:
                try:
                    if source=="csv":
                        stat=Path(path).stat()
                        stamp=(stat.st_size,stat.st_mtime_ns)
                        if stamp==previous:
                            time.sleep(args.interval);continue
                    else:
                        stamp=None  # requery on each interval
                    result=run_pipeline(args.config)
                    previous=stamp
                    print(f"Refreshed {len(result)} outputs at {time.strftime('%H:%M:%S')}",flush=True)
                except (ValueError,OSError,ImportError) as exc:
                    print(f"Monitoring error: {exc}",file=sys.stderr,flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:print("Stopped.")

if __name__=="__main__":main()
