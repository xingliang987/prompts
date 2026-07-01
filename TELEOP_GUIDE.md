TELEOP_GUIDE.md

在sunrise机器上运行这些终端命令

# 终端 1: 机器人 + 控制器 (CAN + arm_moveit)
bash ~/Desktop/testing/launch_teleop.sh
# 等到看到 controller_manager 和 spawner 日志稳定

# 终端 2: 切换到 direct controller (必做!)
ros2 control switch_controllers --deactivate left_arm_controller --activate left_arm_direct_controller
# 看到 "Successfully switched controllers" 才算成功

# 终端 3: XR 数据源
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/apps/roboticsservice/lib:/opt/apps/roboticsservice/SDK/arm64:/opt/apps/roboticsservice
export QT_PLUGIN_PATH=/opt/apps/roboticsservice/plugins
/opt/apps/roboticsservice/RoboticsServiceProcess &

# 终端 4: 臂遥操作
conda activate teleop
cd ~/ros2_ws/src/teleop
python3 teleop_left_arm_direct_vfix.py

# 终端 5: 灵巧手独立控制（终端4 和 终端5 只能同时启动一个）
conda activate teleop
cd ~/ros2_ws/src/teleop
python3 teleop_hand_only.py