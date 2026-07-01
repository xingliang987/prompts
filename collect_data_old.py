#!/usr/bin/env python3
"""collect_data.py — 使用网络机器人的数据采集脚本"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, "/workspace")
from robot_client import NetworkRobot
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset


def main():
    parser = argparse.ArgumentParser(description="机械臂数据采集脚本")
    parser.add_argument("--host", default="192.168.123.101")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--task", default="pick up the red cube")
    parser.add_argument("--output", default="data/my_arm_dataset")
    parser.add_argument("--episode-time", type=float, default=30.0)
    parser.add_argument("--warmup-sec", type=float, default=3.0)
    args = parser.parse_args()

    frame_dt = 1.0 / args.fps
    output_path = Path("/workspace") / args.output

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

    for ep_idx in range(args.episodes):
        input(f"\nEnter -> Episode {ep_idx + 1}/{args.episodes}... ")

        warmup_frames = int(args.warmup_sec * args.fps)
        for _ in range(warmup_frames):
            robot.teleop_step(record_data=False)
            time.sleep(frame_dt)

        start = time.time()
        frame_count = 0
        while time.time() - start < args.episode_time:
            obs, act = robot.teleop_step(record_data=True)
            dataset.add_frame({**obs, **act, "task": args.task})
            frame_count += 1
            elapsed = time.time() - start
            if elapsed < frame_dt * frame_count:
                time.sleep(frame_dt * frame_count - elapsed)

        dataset.save_episode()
        print(f"  Episode {ep_idx + 1} 完成 ({frame_count} 帧)")

    from lerobot.common.datasets.compute_stats import compute_stats
    print("计算统计信息...")
    stats = compute_stats(dataset)
    dataset.meta.save_stats(stats)
    print(f"完成: {output_path}")
    robot.disconnect()


if __name__ == "__main__":
    main()
