from app.minecraft.docker.cgroup import BlockIOStats, MemoryStats
from app.minecraft.docker.network import NetworkStats


def test_memory_stat_preserves_raw_counters_and_used_totals():
    memory = MemoryStats.from_memory_stat_content(
        "anon 100\nfile 200\nkernel 30\ninactive_anon 40\nactive_anon 50\n"
        "inactive_file 60\nactive_file 70\nslab_reclaimable 80\n"
    )
    assert memory.total_memory == 300
    assert memory.active_memory == 120
    assert memory.kernel == 30
    assert memory.inactive_anon == 40
    assert memory.inactive_file == 60
    assert memory.slab_reclaimable == 80
    assert memory.sock == 0
    assert memory.model_dump()["inactive_file"] == 60


def test_block_io_preserves_each_device_and_byte_totals():
    io = BlockIOStats.from_io_stat_content(
        "8:0 rbytes=100 wbytes=200 rios=3 wios=4 dbytes=50 dios=6\n"
        "259:7 rbytes=70 wbytes=80 rios=9 wios=10 dbytes=20 dios=12\n"
    )
    assert [device.model_dump() for device in io.devices] == [
        {"major": 8, "minor": 0, "rbytes": 100, "wbytes": 200, "rios": 3,
         "wios": 4, "dbytes": 50, "dios": 6},
        {"major": 259, "minor": 7, "rbytes": 70, "wbytes": 80, "rios": 9,
         "wios": 10, "dbytes": 20, "dios": 12},
    ]
    assert io.devices[0].device_id == "8:0"
    assert io.devices[1].device_id == "259:7"
    assert io.devices[0].total_bytes == 350
    assert io.total_read_bytes == 170
    assert io.total_write_bytes == 280
    assert io.total_bytes == 520
    assert BlockIOStats.from_io_stat_content("").devices == []


def test_network_stat_preserves_interfaces_and_all_raw_columns():
    network = NetworkStats.from_net_dev_content(4321,
        "Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast\n"
        "lo: 100 2 3 4 5 6 7 8 200 10 11 12 13 14 15 16\n"
        "eth0: 300 18 19 20 21 22 23 24 400 26 27 28 29 30 31 32\n"
        "bad: not numeric 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
        "short: 1 2\n"
    )
    assert network.pid == 4321
    assert [interface.name for interface in network.interfaces] == ["lo", "eth0"]
    assert network.total_rx_bytes == 400
    assert network.total_tx_bytes == 600
    assert network.total_bytes == 1000
    loopback = network.get_interface_by_name("lo")
    assert loopback is not None and loopback.total_bytes == 300
    assert loopback.model_dump() == {
        "name": "lo", "rx_bytes": 100, "rx_packets": 2, "rx_errs": 3,
        "rx_drop": 4, "rx_fifo": 5, "rx_frame": 6, "rx_compressed": 7,
        "rx_multicast": 8, "tx_bytes": 200, "tx_packets": 10, "tx_errs": 11,
        "tx_drop": 12, "tx_fifo": 13, "tx_colls": 14, "tx_carrier": 15,
        "tx_compressed": 16,
    }
    assert network.get_interface_by_name("absent") is None
    assert NetworkStats.from_net_dev_content(4321, "").interfaces == []
