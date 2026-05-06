#!/usr/bin/env python3
"""
Simulador de Rede de Filas — Ana Laura, Fernanda e Leonardo
Trabalho 1 - Simulação e Métodos Analíticos
2026/1
"""
import heapq
import yaml
import sys

# ─────────────────────────────────────────────────────────
# Gerador LCG
# ─────────────────────────────────────────────────────────
class RNG:
    def __init__(self, seed, limit):
        self._a     = 25214903917
        self._c     = 11
        self._m     = 2 ** 48
        self._state = seed & (self._m - 1)
        self._limit = limit
        self._count = 0

    def has_next(self):
        return self._count < self._limit

    def next(self):
        self._state = (self._state * self._a + self._c) & (self._m - 1)
        self._count += 1
        return self._state / self._m

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self.next()

# ─────────────────────────────────────────────────────────
# Fila
# ─────────────────────────────────────────────────────────
class Queue:
    def __init__(self, name, servers, capacity, min_s, max_s):
        self.name       = name
        self.servers    = servers
        self.capacity   = capacity
        self.min_s      = min_s
        self.max_s      = max_s
        self.population = 0
        self.lost       = 0
        self.stats      = {}
        self.routes     = []
        self.min_a      = None
        self.max_a      = None

    def accumulate(self, delta):
        self.stats[self.population] = self.stats.get(self.population, 0.0) + delta

# ─────────────────────────────────────────────────────────
# Simulação
# ─────────────────────────────────────────────────────────
class Simulation:
    def __init__(self, config):
        self.time   = 0.0
        self.queues = {}

        seed  = config.get('seed', 1)
        limit = config.get('rndnumbersPerSeed', 100000)
        self.rng = RNG(seed, limit)

        for name, q_cfg in config['queues'].items():
            cap = q_cfg.get('capacity', None)
            q = Queue(name,
                      servers  = q_cfg['servers'],
                      capacity = cap,
                      min_s    = q_cfg['minService'],
                      max_s    = q_cfg['maxService'])
            if 'minArrival' in q_cfg:
                q.min_a = q_cfg['minArrival']
                q.max_a = q_cfg['maxArrival']
            self.queues[name] = q

        for r in config.get('network', []):
            src  = self.queues[r['source']]
            dest = r['target']
            prob = r['probability']
            src.routes.append((prob, dest))

        self.events = []
        arrivals = config['arrivals']
        for q_name, first_time in arrivals.items():
            heapq.heappush(self.events, (float(first_time), 'ARRIVAL', q_name))

    def _route(self, queue):
        r   = self.rng.next()
        acc = 0.0
        for prob, dest in queue.routes:
            acc += prob
            if r < acc:
                return dest
        return None

    def _schedule_departure(self, queue):
        st = self.rng.uniform(queue.min_s, queue.max_s)
        heapq.heappush(self.events, (self.time + st, 'DEPARTURE', queue.name))

    def _arrival(self, queue):
        if queue.capacity is None or queue.population < queue.capacity:
            queue.population += 1
            if queue.population <= queue.servers:
                self._schedule_departure(queue)
        else:
            queue.lost += 1

        if queue.min_a is not None:
            next_t = self.time + self.rng.uniform(queue.min_a, queue.max_a)
            heapq.heappush(self.events, (next_t, 'ARRIVAL', queue.name))

    def _departure(self, queue):
        queue.population -= 1
        if queue.population >= queue.servers:
            self._schedule_departure(queue)

        dest_name = self._route(queue)
        if dest_name is not None:
            heapq.heappush(self.events, (self.time, 'ARRIVAL', dest_name))

    def run(self):
        while self.events and self.rng.has_next():
            t, etype, q_name = heapq.heappop(self.events)

            delta = t - self.time
            for q in self.queues.values():
                q.accumulate(delta)
            self.time = t

            q = self.queues[q_name]
            if etype == 'ARRIVAL':
                self._arrival(q)
            elif etype == 'DEPARTURE':
                self._departure(q)

# ─────────────────────────────────────────────────────────
# Relatório
# ─────────────────────────────────────────────────────────
def report(sim):
    print("=" * 65)
    print("  QUEUEING NETWORK SIMULATOR")
    print(f"  Aleatórios usados : {sim.rng._count}")
    print(f"  Tempo global      : {sim.time:.4f} min")
    print("=" * 65)

    for name, q in sim.queues.items():
        cap_str = str(q.capacity) if q.capacity is not None else "∞"
        print(f"\n{'*'*65}")
        print(f"  Fila: {q.name} (G/G/{q.servers}/{cap_str})")
        if q.min_a:
            print(f"  Chegada : {q.min_a} ... {q.max_a}")
        print(f"  Serviço : {q.min_s} ... {q.max_s}")
        print(f"{'*'*65}")
        print(f"  {'Estado':>7}  {'Tempo (min)':>18}  {'Probabilidade':>14}")
        for state in sorted(q.stats):
            t = q.stats[state]
            p = (t / sim.time * 100) if sim.time > 0 else 0
            print(f"  {state:>7}  {t:>18.4f}  {p:>13.2f}%")
        print(f"\n  Perdas: {q.lost}")

    print(f"\n{'='*65}")
    print(f"  Simulation average time: {sim.time:.4f}")
    print("=" * 65)

# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def main():
    yml_path = sys.argv[1] if len(sys.argv) > 1 else 'model.yml'
    with open(yml_path) as f:
        raw = f.read().replace('!PARAMETERS\n', '')
    config = yaml.safe_load(raw)

    sim = Simulation(config)
    sim.run()
    report(sim)

if __name__ == '__main__':
    main()
