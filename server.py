#!/usr/bin/env python3

import socket
import threading
import struct
import queue
import time
import datetime

# Разница в секундах между началом отсчет в NTP и UNIX (01.01.1900 - 01.01.1970)
SNTP_DELTA = (datetime.date(1970, 1, 1) - datetime.date(1900, 1, 1)).days * 24 * 60 * 60

OFFSET = 0

PORT = 123


class SNTPPacket:
    PACKET_FORMAT = ">3B b 5I 3Q"

    def __init__(self, transmit_timestamp, orig_timestamp):
        self.leap = 0  # кодовое предупреждение о надвигающейся високосной секунде
        self.version = 4  # номер версии NTP
        self.mode = 4  # 3 - клиент, 4 - сервер
        self.stratum = 2  # Слой (уровень) нашего сервера (1 - первичный сервер, 2 - вторичный)
        self.poll = 0  # Интервал между сообщениями от сервера копируется из запроса клиента
        self.precision = 0  # Точность устанавливается как -ln от значащих бит сервера справа от запятой
        self.root_delay = 0  # Время приема-передачи (RTT)
        self.root_dispersion = 0  # Номинальная ошибка
        self.ref_clock_id = 0  # Идентификатор источника
        self.ref_timestamp = 0  # Время, когда наше время было установлено или поправлено
        if not orig_timestamp:
            self.orig_timestamp = time.time()
        else:
            self.orig_timestamp = 0
        self.receive_timestamp = 0  # Время прихода запроса на сервер
        self.transmit_timestamp = 0  # Время отправки ответа

    def __bytes__(self):
        return struct.pack(SNTPPacket.PACKET_FORMAT,
                           (self.leap << 6 | self.version << 3 | self.mode),
                           self.stratum,
                           self.poll,
                           self.precision,
                           self.root_delay,
                           self.root_dispersion,
                           self.ref_clock_id,
                           self.ref_timestamp,
                           self.ref_timestamp,
                           self.orig_timestamp,
                           SNTPPacket.to_fractional(
                               self.receive_timestamp + OFFSET),
                           SNTPPacket.to_fractional(
                               time.time() + SNTP_DELTA + OFFSET)
                           )

    @classmethod
    def parse_packet(cls, packet):
        if len(packet) < 48:
            return None
        version = (packet[0] & 56) >> 3
        mode = packet[0] & 7
        if mode != 3:
            return None
        transmit_timestamp = int.from_bytes(packet[40:48], 'big')
        original_timestamp = int(time.time() + SNTP_DELTA)
        return SNTPPacket(transmit_timestamp, original_timestamp)

    @classmethod
    def to_fractional(cls, timestamp):
        return int(timestamp * (2 ** 32))


class SNTPServer:
    def __init__(self, port, workers=10):
        self.is_working = True
        self.server_port = port
        self.to_send = queue.Queue()
        self.received = queue.Queue()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', self.server_port))
        self.receiver = threading.Thread(target=self.receive_request)
        self.workers = [threading.Thread(target=self.handle_request) for _ in range(workers)]

    def start(self):
        for w in self.workers:
            w.setDaemon(True)
            w.start()
        self.receiver.setDaemon(True)
        self.receiver.start()
        print(f"listening to {self.server_port} port")
        while self.is_working:
            pass

    def handle_request(self):
        while self.is_working:
            try:
                packet, address = self.received.get(block=False)
            except queue.Empty:
                pass
            else:
                if packet:
                    self.sock.sendto(bytes(packet), address)

    def receive_request(self):
        while self.is_working:
            try:
                data, addr = self.sock.recvfrom(1024)
                self.received.put((SNTPPacket.parse_packet(data), addr))
                print(f'Request:  IP: {addr[0]}  Port: {addr[1]}\n')
            except socket.error:
                return

    def stop(self):
        self.is_working = False
        self.receiver.join()
        for w in self.workers:
            w.join()
        self.server.close()

    def main(self):
        server = SNTPServer(self)
        try:
            server.start()
        except KeyboardInterrupt:
            server.stop()


if __name__ == "__main__":
    try:
        with open('config.txt') as f:
            OFFSET = int(f.readline())
    except Exception as e:
        print('ERROR: {}'.format(e))
    finally:
        print('offset: {} sec.'.format(OFFSET))
    SNTPServer.main(PORT)
