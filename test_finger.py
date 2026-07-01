#!/usr/bin/env python3
"""测试 LinkerHand 手指位置控制"""
import sys, time
sys.path.append("/home/sunrise/linkerhand-python-sdk")
from LinkerHand.linker_hand_api import LinkerHandApi

hand = LinkerHandApi(hand_joint="O6", hand_type="left", can="can0")

before = hand.get_state()
print("Before: " + str(before))

print("\nSetting first finger to 125...")
hand.finger_move(pose=[125, 255, 255, 255, 255, 255])
time.sleep(0.5)
current = hand.get_state()
print("At 125: " + str(current))

print("\nHolding for 5s...")
for i in range(5):
    time.sleep(1)
    cur = hand.get_state()
    print("  t=" + str(i+1) + "s: " + str(cur))

print("\nSetting back to 254...")
hand.finger_move(pose=[254, 255, 254, 254, 254, 254])
time.sleep(0.5)
after = hand.get_state()
print("After: " + str(after))

hand.close_can()
