import json
import pandas as pd

# 将这里的文件名替换为你刚刚解压出来的真实文件名！
with open('sample.json', 'r') as f:
    data = json.load(f)

FEET_TO_METERS = 0.3048
ball_trajectories = []

# 这里提取前50个回合的数据，你可以根据需要改大
for event in data['events'][:50]:
    event_id = event['eventId']
    for moment in event['moments']:
        timestamp = moment[1]
        shot_clock = moment[3]
        
        for entity in moment[5]:
            if entity[0] == -1:  # -1代表篮球
                x_m = entity[2] * FEET_TO_METERS
                y_m = entity[3] * FEET_TO_METERS
                z_m = entity[4] * FEET_TO_METERS
                ball_trajectories.append({
                    'event_id': event_id,
                    'timestamp_ms': timestamp,
                    'shot_clock': shot_clock,
                    'x_m': round(x_m, 3),
                    'y_m': round(y_m, 3),
                    'z_m': round(z_m, 3)
                })

df = pd.DataFrame(ball_trajectories)
df.to_csv('extracted_ball_tracks.csv', index=False)
print("提取完成！已生成 extracted_ball_tracks.csv")