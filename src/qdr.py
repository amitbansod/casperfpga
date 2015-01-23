"""
Created on Fri Mar  7 07:15:45 2014

@author: paulp
"""

import logging
import numpy
import struct
import register

from memory import Memory

LOGGER = logging.getLogger(__name__)

CAL_DATA = [
                [0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,
                 0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,
                 0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,
                 0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,
                 0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,0xAAAAAAAA,0x55555555,
                 0xAAAAAAAA,0x55555555],
                [0,0,0xFFFFFFFF,0,0,0,0,0],
                numpy.arange(256)<<0,
                numpy.arange(256)<<8,
                numpy.arange(256)<<16,
                numpy.arange(256)<<24,
                ]


def find_cal_area(A):
    max_so_far  = A[0]
    max_ending_here = A[0]
    begin_index = 0
    begin_temp = 0
    end_index = 0
    for i in range(len(A)):
        if (max_ending_here < 0):
                max_ending_here = A[i]
                begin_temp = i
        else:
                max_ending_here += A[i]
        if(max_ending_here >= max_so_far ):
                max_so_far  = max_ending_here;
                begin_index = begin_temp;
                end_index = i;
    return max_so_far,begin_index,end_index


class Qdr(Memory):
    """
    Qdr memory on an FPGA.
    """
    def __init__(self, parent, name, address, length, device_info, ctrlreg_address):
        """
        Make the QDR instance, given a parent, name and info from Simulink.
        """
        super(Qdr, self).__init__(name=name, width=32, address=address, length=length)
        self.parent = parent
        self.block_info = device_info
        self.which_qdr = self.block_info['which_qdr']
        self.ctrl_reg = register.Register(self.parent, self.which_qdr+'_ctrl', address=ctrlreg_address,
                                          device_info={'tag': 'xps:sw_reg', 'mode': 'one\_value',
                                                       'io_dir': 'From\_Processor', 'io_delay': '0',
                                                       'sample_period': '1', 'names': 'reg', 'bitwidths': '32',
                                                       'arith_types': '0', 'bin_pts': '0', 'sim_port': 'on',
                                                       'show_format': 'off'})
        self.memory = self.which_qdr + '_memory'
        self.control_mem = self.which_qdr + '_ctrl'
        # self.qdr_cal()
        LOGGER.debug('New Qdr %s' % self)
        # TODO - Link QDR ctrl register to self.registers properly

    @classmethod
    def from_device_info(cls, parent, device_name, device_info, memorymap_dict):
        """
        Process device info and the memory map to get all necessary info and return a Qdr instance.
        :param device_name: the unique device name
        :param device_info: information about this device
        :param memorymap_dict: a dictionary containing the device memory map
        :return: a Qdr object
        """
        mem_address, mem_length = -1, -1
        for mem_name in memorymap_dict.keys():
            if mem_name == device_info['which_qdr'] + '_memory':
                mem_address, mem_length = memorymap_dict[mem_name]['address'], memorymap_dict[mem_name]['bytes']
                break
        if mem_address == -1 or mem_length == -1:
            raise RuntimeError('Could not find address or length for Qdr %s' % device_name)
        # find the ctrl register
        ctrlreg_address, ctrlreg_length = -1, -1
        for mem_name in memorymap_dict.keys():
            if mem_name == device_info['which_qdr'] + '_ctrl':
                ctrlreg_address, ctrlreg_length = memorymap_dict[mem_name]['address'], memorymap_dict[mem_name]['bytes']
                break
        if ctrlreg_address == -1 or ctrlreg_length == -1:
            raise RuntimeError('Could not find ctrl reg  address or length for Qdr %s' % device_name)

        # TODO - is the ctrl reg a register or the whole 256 bytes?

        return cls(parent, device_name, mem_address, mem_length, device_info, ctrlreg_address)

    def __repr__(self):
        return '%s:%s' % (self.__class__.__name__, self.name)

    def reset(self):
        """
        Reset the QDR controller by toggling the lsb of the control register.
        Sets all taps to zero (all IO delays reset).
        """
        LOGGER.debug('qdr reset')
        self.ctrl_reg.write_int(1, blindwrite=True)
        self.ctrl_reg.write_int(0, blindwrite=True)

    def qdr_reset(self):
        "Resets the QDR and the IO delays (sets all taps=0)."
        self.parent.write_int(self.control_mem, 1, blindwrite=True,word_offset=0)
        self.parent.write_int(self.control_mem, 0, blindwrite=True,word_offset=0)


    def qdr_delay_out_step(self,bitmask,step):
        "Steps all bits in bitmask by 'step' number of taps."
        if step >0:
            self.parent.write_int(self.control_mem,(0xffffffff),blindwrite=True,word_offset=7)
        elif step <0:
            self.parent.write_int(self.control_mem,(0),blindwrite=True,word_offset=7)
        else:
            return
        for i in range(abs(step)):
            self.parent.write_int(self.control_mem,0,blindwrite=True,word_offset=6)
            self.parent.write_int(self.control_mem,0,blindwrite=True,word_offset=5)
            self.parent.write_int(self.control_mem,(0xffffffff&bitmask),blindwrite=True,word_offset=6)
            self.parent.write_int(self.control_mem,((0xf)&(bitmask>>32))<<4,blindwrite=True,word_offset=5)

    def qdr_delay_clk_step(self,step):
        "Steps the output clock by 'step' amount."
        if step >0:
            self.parent.write_int(self.control_mem,(0xffffffff),blindwrite=True,word_offset=7)
        elif step <0:
            self.parent.write_int(self.control_mem,(0),blindwrite=True,word_offset=7)
        else:
            return
        for i in range(abs(step)):
            self.parent.write_int(self.control_mem,0,blindwrite=True,word_offset=5)
            self.parent.write_int(self.control_mem,(1<<8),blindwrite=True,word_offset=5)

    def qdr_delay_in_step(self,bitmask,step):
        "Steps all bits in bitmask by 'step' number of taps."
        if step >0:
            self.parent.write_int(self.control_mem,(0xffffffff),blindwrite=True,word_offset=7)
        elif step <0:
            self.parent.write_int(self.control_mem,(0),blindwrite=True,word_offset=7)
        else:
            return
        for i in range(abs(step)):
            self.parent.write_int(self.control_mem,0,blindwrite=True,word_offset=4)
            self.parent.write_int(self.control_mem,0,blindwrite=True,word_offset=5)
            self.parent.write_int(self.control_mem,(0xffffffff&bitmask),blindwrite=True,word_offset=4)
            self.parent.write_int(self.control_mem,((0xf)&(bitmask>>32)),blindwrite=True,word_offset=5)

    def qdr_delay_clk_get(self):
        "Gets the current value for the clk delay."
        raw=self.parent.read_uint(self.control_mem, word_offset=8)
        if (raw&0x1f) != ((raw&(0x1f<<5))>>5):
            raise RuntimeError("Counter values not the same -- logic error! Got back %i."%raw)
        return raw&(0x1f)

    def qdr_cal_check(self,verbosity=0):
        "checks calibration on a qdr. Raises an exception if it failed."
        patfail=0
        for pattern in CAL_DATA:
            self.parent.blindwrite(self.memory,struct.pack('>%iL'%len(pattern),*pattern))
            retdat=struct.unpack('>%iL'%len(pattern), self.parent.read(self.memory,len(pattern)*4))
            for word_n,word in enumerate(pattern):
                patfail=patfail|(word ^ retdat[word_n])
                if verbosity>2:
                    print "{0:032b}".format(word),
                    print "{0:032b}".format(retdat[word_n]),
                    print "{0:032b}".format(patfail)
        if patfail>0:
            #raise RuntimeError ("Calibration of QDR%i failed: 0b%s."%(qdr,"{0:032b}".format(patfail)))
            return False
        else:
            return True


    def find_in_delays(self,verbosity=0):
        n_steps=32
        n_bits=32
        fail=[]
        bit_cal=[[] for bit in range(n_bits)]
        #valid_steps=[[] for bit in range(n_bits)]
        for step in range(n_steps):
            patfail=0
            for pattern in CAL_DATA:
                self.parent.blindwrite(self.memory,struct.pack('>%iL'%len(pattern),*pattern))
                retdat=struct.unpack('>%iL'%len(pattern), self.parent.read(self.memory,len(pattern)*4))
                for word_n,word in enumerate(pattern):
                    patfail=patfail|(word ^ retdat[word_n])
                    if verbosity>2:
                        print '\t %4i %4i'%(step,word_n),
                        print "{0:032b}".format(word),
                        print "{0:032b}".format(retdat[word_n]),
                        print "{0:032b}".format(patfail)
            fail.append(patfail)
            for bit in range(n_bits):
                bit_cal[bit].append(1-2*((fail[step]&(1<<bit))>>bit))
                #if bit_cal[bit][step]==True:
                #    valid_steps[bit].append(step)
            if (verbosity>2):
                print 'STEP input delays to %i!'%(step+1)
            self.qdr_delay_in_step(0xfffffffff,1)

        if (verbosity > 0):
            print 'Eye for QDR %s (0 is pass, 1 is fail):' % self.name
            for step in range(n_steps):
                print '\tTap step %2i: '%step,
                print "{0:032b}".format(fail[step])

        if (verbosity > 3):
            for bit in range(n_bits):
                print 'Bit %2i: '%bit,
                print bit_cal[bit]

        #find indices where calibration passed and failed:
        for bit in range(n_bits):
            try:
                bit_cal[bit].index(1)
            except ValueError:
                raise RuntimeError("Calibration failed for bit %i."%bit)

        #if (verbosity > 0):
        #    print 'valid_steps for bit %i'%(bit),valid_steps[bit]

        cal_steps=numpy.zeros(n_bits+4)
        #find the largest contiguous cal area
        for bit in range(n_bits):
            cal_area=find_cal_area(bit_cal[bit])
            if cal_area[0]<4:
                raise RuntimeError('Could not find a robust calibration setting for QDR %s' % self.name)
            # original was 1/2
            # cal_steps[bit]=sum(cal_area[1:3])/2
            # cal_steps[bit]=sum(cal_area[1:3])/3
            cal_steps[bit]=sum(cal_area[1:3])/4
            if (verbosity > 1):
                print 'Selected tap for bit %i: %i'%(bit,cal_steps[bit])

        # since we don't have access to bits 32-36, we guess the number of taps required based on the other bits:
        # MEDIAN
        median_taps = numpy.median(cal_steps)
        if verbosity > 1:
            print "Median taps: %i" % median_taps
        for bit in range(32, 36):
            cal_steps[bit] = median_taps
            if verbosity > 1:
                print 'Selected tap for bit %i: %i' % (bit, cal_steps[bit])
        # # MEAN
        # mean_taps = numpy.mean(cal_steps)
        # if verbosity > 1:
        #     print "Mean taps: %i" % mean_taps
        # for bit in range(32, 36):
        #     cal_steps[bit] = mean_taps
        #     if verbosity > 1:
        #         print 'Selected tap for bit %i: %i' % (bit, cal_steps[bit])

        return cal_steps

    def apply_cals(self,in_delays,out_delays,clk_delay,verbosity=0):
        #reset all the taps to default (0)
        self.qdr_reset()

        assert len(in_delays)==36
        assert len(out_delays)==36
        self.qdr_delay_clk_step(clk_delay)
        for step in range(int(max(in_delays))):
            mask=0
            for bit in range(len(in_delays)):
                mask+=(1<<bit if (step<in_delays[bit]) else 0)
            if verbosity>1:
                print 'Step %i'%step,
                print "{0:036b}".format(mask)
            self.qdr_delay_in_step(mask,1)

        for step in range(int(max(out_delays))):
            mask=0
            for bit in range(len(out_delays)):
                mask+=(1<<bit if (step<out_delays[bit]) else 0)
            if verbosity>1:
                print 'Step out %i'%step,
                print "{0:036b}".format(mask)
            self.qdr_delay_out_step(mask,1)

    def qdr_cal(self, fail_hard=True, verbosity=0):
        """
        Calibrates a QDR controller, stepping input delays and (if that fails) output delays. Returns True if calibrated, raises a runtime exception if it doesn't.
        :param verbosity:
        :return:
        """
        cal = False
        out_step = 0
        while (not cal) and (out_step < 32):
            # reset all the in delays to zero, and the out delays to this iteration.
            in_delays = [0 for bit in range(36)]
            self.apply_cals(in_delays,
                            out_delays=[out_step for bit in range(36)],
                            clk_delay=out_step,verbosity=verbosity)
            if verbosity > 0:
                print "--- === Trying with OUT DELAYS to %i === ---" % out_step,
                print 'was: %i' % self.qdr_delay_clk_get()
            try:
                in_delays = self.find_in_delays(verbosity)
            except:
                in_delays = [0 for bit in range(36)]
            self.apply_cals(in_delays,
                            out_delays=[out_step for bit in range(36)],
                            clk_delay=out_step,verbosity=verbosity)
            cal = self.qdr_cal_check(verbosity)
            out_step += 1
        if self.qdr_cal_check(verbosity):
            return True
        else:
            if fail_hard:
                raise RuntimeError('QDR %s calibration failed.' % self.name)
            else:
                return False

# end