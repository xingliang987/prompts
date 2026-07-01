import imageio
import torch
from lerobot.common.policies.factory import make_policy
from lerobot.common.envs.factory import make_env

def run_local_simulation():
    # 1. 自动加载专门在 LIBERO 仿真数据集上微调过的 pi-0.5 策略
    policy_id = "lerobot/pi05_libero"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(f"正在加载 pi-0.5 VLA 模型到 {device}...")
    policy = make_policy(repo_id=policy_id, device=device)
    policy.eval()

    # 2. 创建 LIBERO 机械臂仿真环境
    print("正在初始化机械臂仿真器...")
    env = make_env(env_name="libero", task_name="libero_spatial")
    
    # 重置环境，获取第一帧的观测数据（包含 RGB 摄像头图像和机械臂初始状态）
    observation = env.reset()
    done = False
    frames = []

    print("开始闭环仿真测试...")
    step = 0
    while not done and step < 200:  # 限制最大测试步数
        # 渲染当前仿真画面并存入视频帧列表
        img = env.render(mode="rgb_array")
        frames.append(img)

        # 3. VLA 模型前向传播：根据当前图像和文本指令（包含在环境配置中）预测下一步 Action
        with torch.no_grad():
            action = policy.select_action(observation)

        # 4. 仿真器执行动作，并返回执行后的新一帧观测数据
        observation, reward, done, info = env.step(action)
        
        step += 1
        if step % 10 == 0:
            print(f"当前仿真步数: {step}, 奖励得分: {reward}")

    # 5. 将无头渲染下的所有画面保存为本地视频，供你下载到本地查看可视化效果
    video_path = "pi05_performance_rollout.mp4"
    imageio.mimsave(video_path, frames, fps=20)
    print(f"仿真评估结束！可视化视频已成功保存在: {video_path}")

if __name__ == "__main__":
    run_local_simulation()
