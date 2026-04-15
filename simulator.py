#!/usr/bin/env python3
import heapq
import sys
from pathlib import Path

import yaml


class OutOfNumbers(RuntimeError):
    pass


class ListStream:
    def __init__(self, values):
        self._values = list(values)
        self._index = 0

    def has_next(self):
        return self._index < len(self._values)

    def next(self):
        if not self.has_next():
            raise OutOfNumbers("Out of list samples!")
        value = self._values[self._index]
        self._index += 1
        return value


class LinearStream:
    _MULTIPLIER = 25214903917
    _INCREMENT = 11
    _MODULUS = 1 << 48
    _MASK = _MODULUS - 1

    def __init__(self, limit, seed=1):
        self._limit = int(limit)
        self._state = int(seed) & self._MASK
        self._count = 0

    def has_next(self):
        return self._count < self._limit

    def next(self):
        if not self.has_next():
            raise OutOfNumbers("Out of random numbers!")
        self._state = (self._state * self._MULTIPLIER + self._INCREMENT) & self._MASK
        self._count += 1
        return float(self._state) / float(self._MODULUS)


class RandomSource:
    def __init__(self):
        self.stream = None

    def has_next(self):
        return self.stream is not None and self.stream.has_next()

    def next(self):
        if self.stream is None:
            raise OutOfNumbers("No random stream configured!")
        return self.stream.next()

    def next_scaled(self, min_value, max_value):
        sample = self.next()
        return (max_value - min_value) * sample + min_value


class Event:
    def __init__(self, time, event_type, queue, destination=None, sequence=0):
        self.time = time
        self.event_type = event_type
        self.queue = queue
        self.destination = destination
        self.sequence = sequence


class Route:
    def __init__(self, probability, destination):
        self.probability = float(probability)
        self.destination = destination


class Queue:
    def __init__(self, queue_id, environment):
        self.queue_id = queue_id
        self.environment = environment
        self.population = 0
        self.max_population = -1
        self.servers = -1
        self.arrival_min = -1.0
        self.arrival_max = -1.0
        self.service_min = -1.0
        self.service_max = -1.0
        self.destinations = []
        self.statistics = {}
        self.lost = 0

    def __str__(self):
        return self.queue_id

    def add_destination(self, destination, probability):
        self.destinations.append(Route(probability, destination))
        self.destinations.sort(key=lambda route: route.probability)

    def get_destination(self):
        if not self.destinations:
            return None

        first = self.destinations[0]
        if len(self.destinations) == 1 and first.probability >= 1.0:
            return first.destination

        return self._get_destination(self.environment.random_source.next())

    def _get_destination(self, probabilistic_index):
        remaining = probabilistic_index
        for route in self.destinations:
            if remaining <= route.probability:
                return route.destination
            remaining -= route.probability
        return None

    def arrive(self, from_street):
        self.environment.accumulate_time()

        if self.max_population >= 0 and self.population >= self.max_population:
            self.lost += 1
        else:
            self.population += 1
            if self.population <= self.servers:
                self.environment.schedule_departure(self, self.get_destination())

        if from_street:
            self.environment.schedule_arrival(self)

    def depart(self):
        self.environment.accumulate_time()
        self.population -= 1

        if self.population >= self.servers:
            self.environment.schedule_departure(self, self.get_destination())


class Environment:
    def __init__(self):
        self.events = []
        self.initial_events = []
        self.random_source = RandomSource()
        self.time = 0.0
        self.last_event_time = 0.0
        self.accumulated_time = 0.0
        self.queues = {}
        self._sequence = 0

    def _next_sequence(self):
        self._sequence += 1
        return self._sequence

    def add_queue(self, queue_id):
        queue = Queue(queue_id, self)
        self.queues[queue_id] = queue
        return queue

    def get_queue(self, queue_id):
        return self.queues[queue_id]

    def list_queues(self):
        return list(self.queues.keys())

    def schedule_arrival(self, queue, delay=None):
        if delay is None:
            delay = self.random_source.next_scaled(queue.arrival_min, queue.arrival_max)

        event = Event(
            time=self.time + delay,
            event_type="ARRIVAL",
            queue=queue,
            sequence=self._next_sequence(),
        )
        heapq.heappush(self.events, (event.time, event.sequence, event))
        return event

    def schedule_initial_arrival(self, queue, delay):
        event = self.schedule_arrival(queue, delay)
        self.initial_events.append(event)

    def schedule_departure(self, queue, destination, delay=None):
        if delay is None:
            delay = self.random_source.next_scaled(queue.service_min, queue.service_max)

        event = Event(
            time=self.time + delay,
            event_type="DEPARTURE",
            queue=queue,
            destination=destination,
            sequence=self._next_sequence(),
        )
        heapq.heappush(self.events, (event.time, event.sequence, event))
        return event

    def step(self):
        _, _, event = heapq.heappop(self.events)
        self.last_event_time = self.time
        self.time = event.time

        if event.event_type == "ARRIVAL":
            event.queue.arrive(True)
        if event.event_type == "DEPARTURE":
            event.queue.depart()
            if event.destination is not None:
                event.destination.arrive(False)

    def accumulate_time(self):
        delta = self.time - self.last_event_time

        for queue in self.queues.values():
            population = queue.population
            queue.statistics[population] = queue.statistics.get(population, 0.0) + delta

        self.last_event_time = self.time

    def reset(self):
        self.events.clear()
        self.accumulated_time += self.time
        self.time = 0.0
        self.last_event_time = 0.0

        for queue in self.queues.values():
            queue.population = 0

        for event in self.initial_events:
            heapq.heappush(self.events, (event.time, event.sequence, event))


class SimulationParameters:
    def __init__(self):
        self.queues = {}
        self.network = []
        self.arrivals = {}
        self.random_numbers = []
        self.rndnumbers = []
        self.seeds = []
        self.random_numbers_per_seed = None
        self.rndnumbers_per_seed = None

    @staticmethod
    def from_yaml(path):
        content = path.read_text(encoding="utf-8")
        cleaned = content.replace("!PARAMETERS", "", 1)
        data = yaml.safe_load(cleaned) or {}

        parameters = SimulationParameters()
        parameters.queues = data.get("queues", {}) or {}
        parameters.network = data.get("network", []) or []
        parameters.arrivals = data.get("arrivals", {}) or {}
        parameters.random_numbers = data.get("randomNumbers", []) or data.get("rndnumbers", []) or []
        parameters.rndnumbers = data.get("rndnumbers", []) or []
        parameters.seeds = data.get("seeds", []) or []
        parameters.random_numbers_per_seed = data.get("randomNumbersPerSeed")
        parameters.rndnumbers_per_seed = data.get("rndnumbersPerSeed")
        return parameters

    def to_environment(self):
        environment = Environment()

        for queue_id, spec in self.queues.items():
            queue = environment.add_queue(queue_id)
            queue.max_population = int(spec.get("capacity", -1))
            queue.servers = int(spec.get("servers", -1))
            queue.arrival_min = float(spec.get("minArrival", -1.0))
            queue.arrival_max = float(spec.get("maxArrival", -1.0))
            queue.service_min = float(spec.get("minService", -1.0))
            queue.service_max = float(spec.get("maxService", -1.0))

        for route in self.network:
            source = environment.get_queue(route["source"])
            target = environment.get_queue(route["target"])
            source.add_destination(target, float(route["probability"]))

        for queue_id, initial_arrival in self.arrivals.items():
            environment.schedule_initial_arrival(environment.get_queue(queue_id), float(initial_arrival))

        samples = self.random_numbers if self.random_numbers else self.rndnumbers
        environment.random_source.stream = ListStream(samples)
        return environment


def format_number(value, decimals):
    return f"{value:.{decimals}f}".replace(".", ",")


def run_model(model_path):
    parameters = SimulationParameters.from_yaml(model_path)
    environment = parameters.to_environment()

    repetitions = len(parameters.seeds) if parameters.seeds else 1

    for index in range(repetitions):
        if parameters.seeds:
            sample_limit = parameters.random_numbers_per_seed or parameters.rndnumbers_per_seed or 100000
            environment.random_source.stream = LinearStream(sample_limit, int(parameters.seeds[index]))
        else:
            source = parameters.random_numbers if parameters.random_numbers else parameters.rndnumbers
            environment.random_source.stream = ListStream(source)

        try:
            while environment.random_source.has_next():
                environment.step()
        except OutOfNumbers:
            pass

        environment.reset()

    global_time = environment.time + environment.accumulated_time

    for queue_id in environment.list_queues():
        queue = environment.get_queue(queue_id)
        print(f"Queue {queue}:")
        print(f"  losses={queue.lost}")

        states = sorted(queue.statistics.keys())
        if not states:
            print("  no state statistics available")
            continue

        print("  state distribution and accumulated times:")
        for state in states:
            accumulated = queue.statistics[state]
            probability = (accumulated / global_time * 100.0) if global_time > 0.0 else 0.0
            print(
                f"    n={state} -> accumulated={format_number(accumulated, 4)}, "
                f"p(n)={format_number(probability, 2)}%"
            )

    print(f"Global simulation time: {format_number(global_time, 4)}")
    print(f"Average simulation time: {format_number(global_time / repetitions, 4)}")
    return 0


def print_help():
    print("usage:")
    print("  python simulator.py run <modelfilename.yml>")


def main(argv):
    if len(argv) == 0:
        print_help()
        return 0

    if argv[0] != "run":
        print(f"invalid option: {argv}")
        print_help()
        return 0

    if len(argv) < 2:
        print("ERROR: missing file name '.yml'")
        print_help()
        return 2

    model_file = Path(argv[1])
    if not model_file.exists():
        print(f"ERROR: file '{argv[1]}' not found!")
        return 3

    return run_model(model_file)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
