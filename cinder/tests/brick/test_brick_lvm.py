# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mox


from cinder.brick.local_dev import lvm as brick
from cinder.openstack.common import log as logging
from cinder.openstack.common import processutils
from cinder import test
from cinder.volume import configuration as conf

LOG = logging.getLogger(__name__)


def create_configuration():
    configuration = mox.MockObject(conf.Configuration)
    configuration.append_config_values(mox.IgnoreArg())
    return configuration


class BrickLvmTestCase(test.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        self.configuration = mox.MockObject(conf.Configuration)
        self.configuration.volume_group_name = 'fake-volumes'
        super(BrickLvmTestCase, self).setUp()

        #Stub processutils.execute for static methods
        self.stubs.Set(processutils, 'execute',
                       self.fake_execute)
        self.vg = brick.LVM(self.configuration.volume_group_name,
                            'sudo',
                            False, None,
                            'default',
                            self.fake_execute)

    def failed_fake_execute(obj, *cmd, **kwargs):
        return ("\n", "fake-error")

    def fake_pretend_lvm_version(obj, *cmd, **kwargs):
        return ("  LVM version:     2.03.00 (2012-03-06)\n", "")

    def fake_old_lvm_version(obj, *cmd, **kwargs):
        # Does not support thin prov or snap activation
        return ("  LVM version:     2.02.65(2) (2012-03-06)\n", "")

    def fake_customised_lvm_version(obj, *cmd, **kwargs):
        return ("  LVM version:     2.02.100(2)-RHEL6 (2013-09-12)\n", "")

    def fake_execute(obj, *cmd, **kwargs):
        cmd_string = ', '.join(cmd)
        data = "\n"

        if 'vgs, --noheadings, --unit=g, -o, name' == cmd_string:
            data = "  fake-volumes\n"
        elif 'vgs, --noheadings, -o, name' == cmd_string:
            data = "  fake-volumes\n"
        if 'vgs, --version' in cmd_string:
            data = "  LVM version:     2.02.95(2) (2012-03-06)\n"
        elif 'vgs, --noheadings, -o uuid, fake-volumes' in cmd_string:
            data = "  kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1\n"
        elif 'vgs, --noheadings, --unit=g, ' \
             '-o, name,size,free,lv_count,uuid, ' \
             '--separator, :, --nosuffix' in cmd_string:
            data = "  fake-volumes:10.00:10.00:0:"\
                   "kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1\n"
            if 'fake-volumes' in cmd_string:
                return (data, "")
            data += "  fake-volumes-2:10.00:10.00:0:"\
                    "lWyauW-dKpG-Rz7E-xtKY-jeju-QsYU-SLG7Z2\n"
            data += "  fake-volumes-3:10.00:10.00:0:"\
                    "mXzbuX-dKpG-Rz7E-xtKY-jeju-QsYU-SLG8Z3\n"
        elif 'lvs, --noheadings, --unit=g, -o, vg_name,name,size'\
                in cmd_string:
            data = "  fake-volumes fake-1 1.00g\n"
            data += "  fake-volumes fake-2 1.00g\n"
        elif 'lvdisplay, --noheading, -C, -o, Attr' in cmd_string:
            if 'test-volumes' in cmd_string:
                data = '  wi-a-'
            else:
                data = '  owi-a-'
        elif 'pvs, --noheadings' and 'fake-volumes' in cmd_string:
            data = "  fake-volumes:/dev/sda:10.00g:8.99g\n"
        elif 'pvs, --noheadings' in cmd_string:
            data = "  fake-volumes:/dev/sda:10.00g:8.99g\n"
            data += "  fake-volumes-2:/dev/sdb:10.00g:8.99g\n"
            data += "  fake-volumes-3:/dev/sdc:10.00g:8.99g\n"
        elif 'lvs, --noheadings, --unit=g, -o, size,data_percent, ' \
             '--separator, :' in cmd_string:
            data = "  9:12\n"
        else:
            pass

        return (data, "")

    def test_vg_exists(self):
        self.assertEqual(self.vg._vg_exists(), True)

    def test_get_vg_uuid(self):
        self.assertEqual(self.vg._get_vg_uuid()[0],
                         'kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1')

    def test_get_all_volumes(self):
        out = self.vg.get_volumes()

        self.assertEqual(out[0]['name'], 'fake-1')
        self.assertEqual(out[0]['size'], '1.00g')
        self.assertEqual(out[0]['vg'], 'fake-volumes')

    def test_get_volume(self):
        self.assertEqual(self.vg.get_volume('fake-1')['name'], 'fake-1')

    def test_get_all_physical_volumes(self):
        pvs = self.vg.get_all_physical_volumes('sudo')
        self.assertEqual(len(pvs), 3)

    def test_get_physical_volumes(self):
        pvs = self.vg.get_physical_volumes()
        self.assertEqual(len(pvs), 1)

    def test_get_volume_groups(self):
        self.assertEqual(len(self.vg.get_all_volume_groups('sudo')), 3)
        self.assertEqual(len(self.vg.get_all_volume_groups('sudo',
                                                           'fake-volumes')), 1)

    def test_thin_support(self):
        # lvm.supports_thin() is a static method and doesn't
        # use the self._executor fake we pass in on init
        # so we need to stub processutils.execute appropriately

        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertTrue(self.vg.supports_thin_provisioning('sudo'))

        self.stubs.Set(processutils, 'execute', self.fake_pretend_lvm_version)
        self.assertTrue(self.vg.supports_thin_provisioning('sudo'))

        self.stubs.Set(processutils, 'execute', self.fake_old_lvm_version)
        self.assertFalse(self.vg.supports_thin_provisioning('sudo'))

        self.stubs.Set(processutils,
                       'execute',
                       self.fake_customised_lvm_version)
        self.assertTrue(self.vg.supports_thin_provisioning('sudo'))

    def test_snapshot_lv_activate_support(self):
        self.vg._supports_snapshot_lv_activation = None
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertTrue(self.vg.supports_snapshot_lv_activation)

        self.vg._supports_snapshot_lv_activation = None
        self.stubs.Set(processutils, 'execute', self.fake_old_lvm_version)
        self.assertFalse(self.vg.supports_snapshot_lv_activation)

        self.vg._supports_snapshot_lv_activation = None

    def test_lvchange_ignskipact_support_yes(self):
        """Tests the ability to test support for lvchange -K

        Stubs provide output for "lvchange --help".
        """

        def lvchange_ign_yes(obj, *args, **kwargs):
            return ("""
              WARNING: Running as a non-root user. Functionality may be
              unavailable.
              lvchange: Change the attributes of logical volume(s)

            lvchange
                [-A|--autobackup y|n]
                [-k|--setactivationskip {y|n}]
                [-K|--ignoreactivationskip]
                [-y|--yes]
                [-Z|--zero {y|n}]
                LogicalVolume[Path] [LogicalVolume[Path]...]
            """, "")

        self.vg._supports_lvchange_ignoreskipactivation = None
        self.stubs.Set(self.vg, '_execute', lvchange_ign_yes)
        self.assertTrue(self.vg.supports_lvchange_ignoreskipactivation)

        self.vg._supports_lvchange_ignoreskipactivation = None

    def test_lvchange_ignskipact_support_no(self):
        def lvchange_ign_no(obj, *args, **kwargs):
            return ("""
              WARNING: Running as a non-root user. Functionality may be
              unavailable.
              lvchange: Change the attributes of logical volume(s)

            lvchange
                [-A|--autobackup y|n]
                [-k|--setactivationskip {y|n}]
                [-y|--yes]
                [-Z|--zero {y|n}]
                LogicalVolume[Path] [LogicalVolume[Path]...]
            """, "")

        self.vg._supports_lvchange_ignoreskipactivation = None
        self.stubs.Set(self.vg, '_execute', lvchange_ign_no)
        self.assertFalse(self.vg.supports_lvchange_ignoreskipactivation)

        self.vg._supports_lvchange_ignoreskipactivation = None

    def test_thin_pool_creation(self):

        # The size of fake-volumes volume group is 10g, so the calculated thin
        # pool size should be 9.5g (95% of 10g).
        self.assertEqual("9.5g", self.vg.create_thin_pool())

        # Passing a size parameter should result in a thin pool of that exact
        # size.
        for size in ("1g", "1.2g", "1.75g"):
            self.assertEqual(size, self.vg.create_thin_pool(size_str=size))

    def test_thin_pool_free_space(self):
        # The size of fake-volumes-pool is 9g and the allocated data sums up to
        # 12% so the calculated free space should be 7.92
        self.assertEqual(float("7.92"),
                         self.vg._get_thin_pool_free_space("fake-vg",
                                                           "fake-vg-pool"))

    def test_volume_create_after_thin_creation(self):
        """Test self.vg.vg_thin_pool is set to pool_name

        See bug #1220286 for more info.
        """

        vg_name = "vg-name"
        pool_name = vg_name + "-pool"
        pool_path = "%s/%s" % (vg_name, pool_name)

        def executor(obj, *cmd, **kwargs):
            self.assertEqual(pool_path, cmd[-1])

        self.vg._executor = executor
        self.vg.create_thin_pool(pool_name, "1G")
        self.vg.create_volume("test", "1G", lv_type='thin')

        self.assertEqual(self.vg.vg_thin_pool, pool_name)

    def test_lv_has_snapshot(self):
        self.assertTrue(self.vg.lv_has_snapshot('fake-volumes'))
        self.assertFalse(self.vg.lv_has_snapshot('test-volumes'))

    def test_activate_lv(self):
        self._mox.StubOutWithMock(self.vg, '_execute')
        self.vg._supports_lvchange_ignoreskipactivation = True

        self.vg._execute('lvchange', '-a', 'y', '--yes', '-K',
                         'fake-volumes/my-lv',
                         root_helper='sudo', run_as_root=True)

        self._mox.ReplayAll()

        self.vg.activate_lv('my-lv')

        self._mox.VerifyAll()
