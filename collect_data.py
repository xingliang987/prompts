#!/usr/bin/env python3
"""collect_data.py — VR 遥操数据采集（同一 prompt 用于所有 episodes）"""
import argparse
import os
import sys
import time
import select
from pathlib import Path

sys.path.insert(0, "/workspace")
from robot_client import NetworkRobot
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset


def main():
    parser = argparse.ArgumentParser(description="机械臂数据采集脚本 (VR 遥操)")
    parser.add_argument("--host", default=os.environ.get("ROBOT_HOST", "192.168.127.66"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--task", default="",
                        help="任务描述（所有 episodes 共用；留空则在启动时输入一次）")
    parser.add_argument("--output", default="data/my_arm_dataset")
    parser.add_argument("--warmup-sec", type=float, default=3.0)
    parser.add_argument("--max-episode-sec", type=float, default=0,
                        help="最长录制时间（秒，0=不限，按 Enter 停止）")
    args = parser.parse_args()

    frame_dt = 1.0 / args.fps
    output_path = Path("/workspace") / args.output

    # 确定 prompt — 所有 episodes 共用同一个
    if args.task:
        prompt = args.task
        print(f"任务: \"{prompt}\"（{args.episodes} episodes）")
    else:
        prompt = input("任务描述: ").strip()
        if not prompt:
            prompt = "(no task)"

    print(f"连接 {args.host}:{args.port}...")
    robot = NetworkRobot(host=args.host, port=args.port)
    robot.connect()
    print("连接成功")

    output_path.mkdir(parents=True, exist_ok=True)
    dataset = LeRobotDataset.create(
        repo_id=args.output.replace("/", "_"),
        fps=args.fps,
        robot=robot,
        use_videos=True,
        root=str(output_path),
    )
    print(f"数据集保存: {output_path}")
    if args.max_episode_sec > 0:
        print(f"最长录制: {args.max_episode_sec}s / ep（超时自动保存）")
    else:
        print("按 Enter 停止当前 episode")

    for ep_idx in range(args.episodes):
        print(f"\nEpisode {ep_idx + 1}/{args.episodes} — \"{prompt}\"")
        # 倒计时准备
        for s in range(3, 0, -1):
            print(f"  {s}...", end=" ", flush=True)
            time.sleep(1)
        print("开始")

        # 预热（不录）
        warmup_frames = int(args.warmup_sec * args.fps)
        for _ in range(warmup_frames):
            robot.teleop_step(record_data=False)
            time.sleep(frame_dt)

        # 录制
        print("录制中... 按 Enter 停止", end="", flush=True)
        start = time.time()
        frame_count = 0
        stop = False
        while not stop:
            obs, act = robot.teleop_step(record_data=True)
            dataset.add_frame({**obs, **act, "task": prompt})
            frame_count += 1

            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                stop = True

            if args.max_episode_sec > 0 and time.time() - start > args.max_episode_sec:
                print(f" (超时)", end="")
                stop = True

            elapsed = time.time() - start
            print(f"\r  已录 {frame_count} 帧 ({elapsed:.1f}s)", end="", flush=True)
            target_sleep = frame_dt * frame_count - elapsed
            while target_sleep > 0:
                time.sleep(min(0.05, target_sleep))
                target_sleep -= 0.05
                if select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.readline()
                    stop = True
                    break

        dataset.save_episode()
        print(f"\n  Episode {ep_idx + 1} 保存 ({frame_count} 帧, {time.time()-start:.1f}s)")

    from lerobot.common.datasets.compute_stats import compute_stats
    print("\n计算统计信息...")
    stats = compute_stats(dataset)
    dataset.meta.save_stats(stats)
    print(f"完成: {output_path}")
    robot.disconnect()


if __name__ == "__main__":
    main()
