import torch

xs = torch.tensor([1.0, 2.0, 3.0])
ys = torch.tensor([3.0, 6.0, 9.0])

w = torch.tensor(0.0, requires_grad=True)  # start with a bad guess
lr = 0.01  # learning rate: how big each nudge is

for step in range(50):
    pred = w * xs  # 1. predict
    loss = ((pred - ys) ** 2).mean()  # 2. how wrong are we?
    loss.backward()  # 3. compute the gradient, stored in w.grad
    with torch.no_grad():
        w -= lr * w.grad  # 4. nudge w downhill
    w.grad.zero_()  # clear it for the next step
    if step % 10 == 0:
        print(f"step {step:2d} | w = {w.item():.3f} | loss = {loss.item():.3f}")

print("learned w:", round(w.item(), 3))
