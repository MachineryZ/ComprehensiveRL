class DoubleDQN(object):
    def __init__(
        self,
        env_name: str,
        capacity: int,
        train_epochs: int,
        test_epochs: int,
        max_iterations: int,
        epsilon_start: float,
        epsilon_end: float,
        epsilon_decay: float,
        hidden_dim: int,
        lr: float,
        bias: bool,
        seed: int,
        update_epoch: int,
        batch_size: int,
        gamma: float,
    ):
        self.env = gym.make(env_name)
        self.capacity = capacity
        self.train_epochs = train_epochs
        self.test_epochs = test_epochs
        self.max_iterations = max_iterations
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.update_epoch = update_epoch
        self.batch_size = batch_size
        self.gamma = gamma

        torch.manual_seed(seed)
        self.env.seed(seed)
        self.input_dim = input_dim = self.env.observation_space.shape[0]
        self.output_dim = output_dim = self.env.action_space.n
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.policy_net = MLP(input_dim, hidden_dim, output_dim, bias).to(self.device)
        self.target_net = MLP(input_dim, hidden_dim, output_dim, bias).to(self.device)
        # Copy the parameters:
        for target_param, param in zip(self.target_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(param.data)
        self.optimizer = torch.optim.Adam(self.policy_net.parameters(), lr=lr)
        self.memory = ReplayBuff(capacity)

        self.frame_idx = 1

    def get_epsilon(self):
        self.frame_idx += 1
        epsilon = self.epsilon_end + (self.epsilon_start - self.epsilon_end) * \
            math.exp(-1. * self.frame_idx / self.epsilon_decay)
        return epsilon

    def choose_action(self, state, mode):
        if mode == "train":
            epsilon = self.get_epsilon()
            if random.random() > epsilon:
                with torch.no_grad():
                    state = torch.tensor(np.array([state]), device=self.device, dtype=torch.float32)
                    q_values = self.policy_net(state)
                    action = q_values.max(1)[1].item()
            else:
                action = random.randrange(self.output_dim)
            return action
        else:
            with torch.no_grad():
                state = torch.tensor(np.array([state]), device=self.device, dtype=torch.float32)
                q_values = self.policy_net(state)
                action = q_values.max(1)[1].item()
            return action

    def update(self):
        if len(self.memory) < self.batch_size:
            return
        state_batch, action_batch, reward_batch, next_state_batch, done_batch = self.memory.sample(self.batch_size)
        state_batch = torch.tensor(state_batch, device=self.device, dtype=torch.float)
        action_batch = torch.tensor(action_batch, device=self.device).unsqueeze(1)
        reward_batch = torch.tensor(reward_batch, device=self.device, dtype=torch.float)
        next_state_batch = torch.tensor(next_state_batch, device=self.device, dtype=torch.float)
        done_batch = torch.tensor(np.float32(done_batch), device=self.device)

        # DQN:
        # q_values = self.policy_net(state_batch).gather(dim=1, index=action_batch)
        # next_q_values = self.target_net(next_state_batch).max(1)[0].detach()
        # expected_q_values = reward_batch + self.gamma * next_q_values * (1 - done_batch)
        # loss = nn.MSELoss()(q_values, expected_q_values.unsqueeze(1))

        q_values = self.policy_net(state_batch)
        next_q_values = self.policy_net(next_state_batch)
        q_value = q_values.gather(dim=1, index=action_batch)
        next_target_values = self.target_net(next_state_batch)
        next_target_q_value = next_target_values.gather(1, torch.max(next_q_values, 1)[1].unsqueeze(1)).squeeze(1)
        q_target = reward_batch + self.gamma * (next_target_q_value) * (1 - done_batch)
        loss = nn.MSELoss()(q_value, q_target.unsqueeze(1))

        self.optimizer.zero_grad()
        loss.backward()
        for param in self.policy_net.parameters():
            param.grad.data.clamp_(-1, 1)
        self.optimizer.step()

    def train(self):
        rewards = []
        ma_rewards = []
        for num_epoch in range(self.train_epochs):
            epoch_reward = 0
            state = self.env.reset()
            for i in range(self.max_iterations):
                action = self.choose_action(state, "train")
                next_state, reward, done, info = self.env.step(action)
                self.memory.push(state, action, reward, next_state, done)
                state = next_state
                self.update()
                epoch_reward += reward
                if done:
                    break
            rewards.append(epoch_reward)
            if ma_rewards:
                ma_rewards.append(0.9 * ma_rewards[-1] + 0.1 * epoch_reward)
            else:
                ma_rewards.append(epoch_reward)
            if num_epoch % self.update_epoch == 0:
                self.target_net.load_state_dict(self.policy_net.state_dict())
        self.plot(rewards, mode="train", extra="na")
        self.plot(ma_rewards, mode="train", extra="ma")

    def test(self):
        rewards = []
        ma_rewards = []
        for num_epoch in range(self.test_epochs):
            epoch_reward = 0.0
            state = self.env.reset()
            for i in range(self.max_iterations):
                action = self.choose_action(state, "test")
                next_state, reward, done, info = self.env.step(action)
                state = next_state
                epoch_reward += reward
                if done:
                    break
            rewards.append(epoch_reward)
            if ma_rewards:
                ma_rewards.append(ma_rewards[-1] * 0.9 + epoch_reward * 0.1)
            else:
                ma_rewards.append(epoch_reward)
        self.plot(rewards, mode="test", extra="na")
        self.plot(ma_rewards, mode="test", extra="ma")

    def plot(self, reward_list, mode: str, extra = str):
        if mode == 'train':
            plt.figure()
            plt.title(f"train learning curve of policy gradient for cartpole {extra}")
            plt.plot(reward_list)
            plt.savefig(f"chapter_7_DoubleDQN_train {extra}.png")
        elif mode == 'test':
            plt.figure()
            plt.title(f"test learning curve of policy gradient for cartpole {extra}")
            plt.plot(reward_list)
            plt.savefig(f"chapter_7_DoubleDQN_test {extra}.png")
