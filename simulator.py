#!/usr/bin/env python3
import heapq
import yaml
import sys

class LinearStream:
    def __init__(self, limit, seed=1):
        self._limit = limit
        self._state = seed & 0xFFFFFFFFFFFF
        self._count = 0
        self._multiplier = 25214903917
        self._increment = 11
        self._modulus = 1 << 48

    def has_next(self):
        return self._count < self._limit

    def next(self):
        if not self.has_next(): return None
        self._state = (self._state * self._multiplier + self._increment) & (self._modulus - 1)
        self._count += 1
        return float(self._state) / float(self._modulus)

class Queue:
    def __init__(self, name, servers, capacity, min_s, max_s):
        self.name = name
        self.servers = servers
        self.capacity = capacity
        self.min_s = min_s
        self.max_s = max_s
        self.population = 0
        self.lost = 0
        self.stats = {}
        self.routes = []

    def update_stats(self, delta):
        self.stats[self.population] = self.stats.get(self.population, 0.0) + delta

class Simulation:
    def __init__(self, config):
        self.time = 0.0
        self.last_time = 0.0
        self.rnd = LinearStream(config['randomNumbersLimit'], config.get('seed', 1))
        self.queues = {}
        
        for name, q_cfg in config['queues'].items():
            self.queues[name] = Queue(name, q_cfg['servers'], q_cfg['capacity'], 
                                     q_cfg['minService'], q_cfg['maxService'])
            if 'minArrival' in q_cfg:
                self.queues[name].min_a = q_cfg['minArrival']
                self.queues[name].max_a = q_cfg['maxArrival']

        for r in config['network']:
            self.queues[r['source']].routes.append((r['probability'], r['target']))

        self.events = []
        start_q = self.queues[config['arrivals']['queue']]
        heapq.heappush(self.events, (config['arrivals']['firstTime'], "ARRIVAL", start_q.name))

    def get_rnd(self, a, b):
        return (b - a) * self.rnd.next() + a

    def run(self):
        while self.events and self.rnd.has_next():
            t, type, q_name = heapq.heappop(self.events)
            delta = t - self.time
            for q in self.queues.values(): q.update_stats(delta)
            self.time = t

            curr_q = self.queues[q_name]

            if type == "ARRIVAL":
                if curr_q.capacity == -1 or curr_q.population < curr_q.capacity:
                    curr_q.population += 1
                    if curr_q.population <= curr_q.servers:
                        self.schedule_departure(curr_q)
                else:
                    curr_q.lost += 1
                
                if hasattr(curr_q, 'min_a'):
                    next_t = self.time + self.get_rnd(curr_q.min_a, curr_q.max_a)
                    heapq.heappush(self.events, (next_t, "ARRIVAL", curr_q.name))

            elif type == "DEPARTURE":
                curr_q.population -= 1
                if curr_q.population >= curr_q.servers:
                    self.schedule_departure(curr_q)
                
                # Roteamento Variável
                r_val = self.rnd.next()
                acc = 0
                for prob, target in curr_q.routes:
                    acc += prob
                    if r_val <= acc:
                        if target: heapq.heappush(self.events, (self.time, "ARRIVAL", target))
                        break

    def schedule_departure(self, queue):
        st = self.get_rnd(queue.min_s, queue.max_s)
        heapq.heappush(self.events, (self.time + st, "DEPARTURE", queue.name))

def main():
    with open("model.yml", 'r') as f:
        config = yaml.safe_load(f)
    
    sim = Simulation(config)
    sim.run()

    print(f"Tempo Global: {sim.time:.4f}\n")
    for q in sim.queues.values():
        print(f"Fila {q.name}: Perdas = {q.lost}")
        for state in sorted(q.stats.keys()):
            p = (q.stats[state] / sim.time) * 100
            print(f"  n={state} -> Tempo: {q.stats[state]:.4f} | Prob: {p:.2f}%")
        print("-" * 30)

if __name__ == "__main__":
    main()
