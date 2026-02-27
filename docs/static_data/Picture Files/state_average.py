# -*- coding: utf-8 -*-
"""
Created on Wed Feb 19 19:03:33 2025

@author: ehakm
"""
import matplotlib.patches as patches
import matplotlib.pyplot as plt


# Calculate the average basis for each state
state_averages = numeric_rows.groupby('State')['Adj_Basis'].mean().reset_index()
state_count = numeric_rows.groupby('State')['Adj_Basis'].count().reset_index()
count = state_count['Adj_Basis'].sum()

# Sort the state averages in descending order
state_averages = state_averages.sort_values(by='Adj_Basis', ascending=True)

#Create the state average chart

# Plotti
plt.figure(figsize=(8, 6))
ax = plt.gca()

# Plot bars with colors based on sign
y_positions = range(len(state_averages))
colors = ['navy' if v > 0 else 'darkred' for v in state_averages['Adj_Basis']]
plt.barh(y_positions, state_averages['Adj_Basis'], color=colors)

# Move the Y-axis (left spine) to the center (x=0)
ax.spines['left'].set_position(('data', 0))
ax.spines['left'].set_color('white')
ax.spines['left'].set_linewidth(15)

# Hide other spines
ax.spines['right'].set_color('none')
ax.spines['top'].set_color('none')
ax.spines['bottom'].set_color('none')
ax.xaxis.set_visible(False)

# Hide default y-axis ticks
ax.set_yticks([])

# Add state names as ribbons over the center line with transparent white background
for i, state in enumerate(state_averages['State']):
    ax.text(0, i, state, va='center', ha='center', color='black', fontsize=12, fontweight='bold',
            bbox=dict(facecolor='white', edgecolor='none', boxstyle='square,pad=0.5'))

# Add data labels at the end of each bar (CURRENCY FORMAT)
for i, v in enumerate(state_averages['Adj_Basis']):
    ha = 'left' if v > 0 else 'right'
    label_color = 'navy' if v > 0 else 'darkred'
    if v >= 0:
        label = f"${v:.2f}"
    else:
        label = f"(${abs(v):.2f})"

    ax.text(v, i, label, va='center', ha=ha, color=label_color, fontsize=10, fontweight='bold')

# Optional: Add a subtle vertical line at x=0
ax.axvline(x=0, color='black', linestyle='-', linewidth=0.8, alpha=0.5)

plt.title(f'Average Adjusted Basis by State \nTotal Count: {count}', fontsize=15, fontweight='bold')


plt.tight_layout()

# ✅ Add a Blue Frame (Border) Around the Entire Plot Area
# Get plot limits and draw a rectangle
x0, x1 = ax.get_xlim()
y0, y1 = ax.get_ylim()

padding_x = (x1 - x0) * 0.05  # 5% padding horizontally
padding_y = (y1 - y0) * 0.0  # 5% padding vertically

border = patches.Rectangle(
    (x0 - padding_x, y0 - padding_y),  # Start lower left corner
    (x1 - x0) + 2 * padding_x,         # Width with padding
    (y1 - y0) + 2 * padding_y,         # Height with padding
    linewidth=3,
    edgecolor='blue',
    facecolor='none',
    zorder=10,
    clip_on=False
)

ax.add_patch(border)



state_avg_path =   r"C:\Users\ehakm\OneDrive\Documents\Python Code\state_avg.png"
plt.savefig(state_avg_path, dpi=300, bbox_inches='tight', transparent=False)
plt.show()

print(r"C:\Users\ehakm\OneDrive\Documents\Python Code\state_avg.png")