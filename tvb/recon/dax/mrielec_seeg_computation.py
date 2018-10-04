# -*- coding: utf-8 -*-

from Pegasus.DAX3 import File, Job, Link

from tvb.recon.dax.mappings import Inputs, MriElecSEEGCompFiles, MriElecSEEGCompJobNames, T1Files, CoregJobNames, \
    SEEGCompJobNames
from tvb.recon.dax.qc_snapshots import QCSnapshots


class MriElecSEEGComputation(object):

    def __init__(self, subj, mrielec_frmt, same_space_vol_pom, dilate=0, erode=0):
        self.subj = subj
        self.mrielec_frmt = mrielec_frmt
        self.same_space_vol_pom = same_space_vol_pom
        dilate=int(float(dilate))
        erode = int(float(erode))
        assert (erode >= 0 and dilate >= 0), "Parameter erode(=%s) and/or dilate(=%s) for mrielec binarization " \
                                           "is negative!" % (str(erode), str(dilate))
        assert (erode < dilate or erode == 0), "Non zero parameter erode(=%s) is not smaller than dilate(=%s) " \
                                               "for mrielec binarization!" % (str(erode), str(dilate))
        self.dilate = int(dilate)
        self.erode = int(erode)
        self.qc_snapshots = QCSnapshots.get_instance()

    def add_computation_steps(self, dax, job_t1):

        mrielec_vol = File(Inputs.MRIELEC_INPUT.value)
        elecs_pom = File(Inputs.ELECS_POM.value)

        t1_nii_gz = File(T1Files.T1_NII_GZ.value)
        mrielec_to_t1_mat = File(MriElecSEEGCompFiles.MRIELEC_TO_T1_MAT.value)
        mrielec_in_t1_nii_gz = File(MriElecSEEGCompFiles.MRIELEC_IN_T1_VOL.value)
        job1 = Job(CoregJobNames.FLIRT.value, node_label="flirt register MRIelectrode to T1")
        job1.addArguments(mrielec_vol, t1_nii_gz, mrielec_to_t1_mat, mrielec_in_t1_nii_gz)
        job1.uses(mrielec_vol, Link.INPUT)
        job1.uses(t1_nii_gz, Link.INPUT)
        job1.uses(mrielec_to_t1_mat, Link.OUTPUT, transfer=True, register=True)
        job1.uses(mrielec_in_t1_nii_gz, Link.OUTPUT, transfer=True, register=True)

        dax.addJob(job1)
        dax.depends(job1, job_t1)

        self.qc_snapshots.add_2vols_snapshot_step(dax, [job1], mrielec_in_t1_nii_gz, t1_nii_gz, "mrielec_in_t1")

        seeg_pom_xyz_txt = File(MriElecSEEGCompFiles.SEEG_POM_XYZ_TXT.value)
        seeg_pom_vol = File(MriElecSEEGCompFiles.SEEG_POM_VOL.value)

        arguments_dilate_erode = []
        if self.dilate > 0:
            arguments_dilate_erode.append("--dilate")
            arguments_dilate_erode.append(str(self.dilate))
        if self.erode > 0:
            arguments_dilate_erode.append("--erode")
            arguments_dilate_erode.append(str(self.erode))

        if self.same_space_vol_pom == "True":

            # In this case pom space is the same as mrielec space,
            # therefore extract seeg coordinates and assign them to a dummy volume in the original MRIelectrode space

            job2 = Job(MriElecSEEGCompJobNames.EXTRACT_POSITIONS_FROM_POM.value,
                       node_label="Extract SEEG coordinates from pom file to a MRIelectrode-like volume")
            job2.addArguments(elecs_pom, seeg_pom_xyz_txt, mrielec_vol, seeg_pom_vol)
            job2.uses(elecs_pom, Link.INPUT)
            job2.uses(mrielec_vol, Link.INPUT)
            job2.uses(seeg_pom_xyz_txt, Link.OUTPUT, transfer=True, register=True)
            job2.uses(seeg_pom_vol, Link.OUTPUT, transfer=True, register=True)

            dax.addJob(job2)

            # Now all is needed is to  transform the seeg pom coordinates to T1 space
            seeg_pom_to_t1 = mrielec_to_t1_mat

            last_job = job2
       
        else:

            # In this case pom space is NOT the same as mrielec space.
            # Therefore, we can assign seeg pom coordinates already to a dummy volume in the MRIelectrode_in_t1 space.
            # Then all we need is to register this dummy volume to MRIelectrode_in_t1
            # and thus, transform the seeg pom coordinates to T1 space

            job2 = Job(MriElecSEEGCompJobNames.EXTRACT_POSITIONS_FROM_POM.value,
                       node_label="Extract SEEG coordinates from pom file to a MRIelectrode_in_t1-like volume")
            job2.addArguments(elecs_pom, seeg_pom_xyz_txt, mrielec_in_t1_nii_gz, seeg_pom_vol)
            job2.uses(elecs_pom, Link.INPUT)
            job2.uses(mrielec_in_t1_nii_gz, Link.INPUT)
            job2.uses(seeg_pom_xyz_txt, Link.OUTPUT, transfer=True, register=True)
            job2.uses(seeg_pom_vol, Link.OUTPUT, transfer=True, register=True)

            dax.addJob(job2)
            dax.depends(job2, job1)

            # Binarize the seeg pom volume (it originally has values increasing from 1 to the number of seeg contacts)
            seeg_pom_bin_vol = File(MriElecSEEGCompFiles.SEEG_POM_BIN_VOL.value)
            job3 = Job(SEEGCompJobNames.MRI_BINARIZE.value, node_label="mri_binarize seeg pom volume")

            arguments_list = ["--i", seeg_pom_vol, "--o", seeg_pom_bin_vol, "--min", "1"] + arguments_dilate_erode
            job3.addArguments(*tuple(arguments_list))
            job3.uses(seeg_pom_vol, Link.INPUT)
            job3.uses(seeg_pom_bin_vol, Link.OUTPUT, transfer=True, register=True)

            dax.addJob(job3)
            dax.depends(job3, job2)

            mrielec_bin_vol = File(MriElecSEEGCompFiles.MRIELEC_BIN_VOL.value)

            # For the threshold value to work, the MRIelectrode binarization has to happen on the original volume...

            job4 = Job(SEEGCompJobNames.MRI_BINARIZE.value, node_label="mri_binarize MRIelectrode")

            arguments_list = ["--i", mrielec_vol, "--o", mrielec_bin_vol, "--min", "max"] + arguments_dilate_erode
            job4.addArguments(*tuple(arguments_list))
            job4.uses(mrielec_vol, Link.INPUT)
            job4.uses(mrielec_bin_vol, Link.OUTPUT, transfer=True, register=True)

            dax.addJob(job4)

            dax.depends(job4, job1)

            # ...and only then register the binarized volume to t1 space
            mrielec_bin_in_t1_nii_gz = File(MriElecSEEGCompFiles.MRIELEC_BIN_IN_T1_VOL.value)

            job5 = Job(CoregJobNames.FLIRT_APPLYXFM.value, node_label="flirt transform binarized MRIelectrode to t1")
            job5.addArguments(mrielec_bin_vol, t1_nii_gz, mrielec_bin_in_t1_nii_gz, mrielec_to_t1_mat)
            job5.uses(mrielec_bin_vol, link=Link.INPUT)
            job5.uses(t1_nii_gz, link=Link.INPUT)
            job5.uses(mrielec_to_t1_mat, link=Link.INPUT)
            job5.uses(mrielec_bin_in_t1_nii_gz, link=Link.OUTPUT, transfer=True, register=True)
            dax.addJob(job5)

            dax.depends(job5, job4)

            self.qc_snapshots.add_2vols_snapshot_step(dax, [job5],
                                                      mrielec_bin_in_t1_nii_gz, t1_nii_gz, "mrielec_bin_in_t1")

            # This is the most tricky part: register the two binary volumes together,
            #  the seeg pom one to the MRIelectrode_in_t1
            seeg_pom_to_t1 = File(MriElecSEEGCompFiles.SEEG_POM_TO_T1_MAT.value)
            seeg_pom_bin_in_t1_nii_gz = File(MriElecSEEGCompFiles.SEEG_POM_BIN_IN_T1_VOL.value)

            job_coreg = Job(CoregJobNames.FLIRT.value,
                            node_label="flirt register seeg pom to binarized MRIelectrode_in_t1")
            job_coreg.addArguments(seeg_pom_bin_vol, mrielec_bin_in_t1_nii_gz,
                                   seeg_pom_to_t1, seeg_pom_bin_in_t1_nii_gz, "corratio")
            job_coreg.uses(seeg_pom_bin_vol, Link.INPUT)
            job_coreg.uses(mrielec_bin_in_t1_nii_gz, Link.INPUT)
            job_coreg.uses(seeg_pom_to_t1, Link.OUTPUT, transfer=True, register=True)
            job_coreg.uses(seeg_pom_bin_in_t1_nii_gz, Link.OUTPUT, transfer=True, register=True)

            dax.addJob(job_coreg)
            dax.depends(job_coreg, job3)
            dax.depends(job_coreg, job5)

            self.qc_snapshots.add_2vols_snapshot_step(dax, [job_coreg],
                                                      seeg_pom_bin_in_t1_nii_gz, mrielec_in_t1_nii_gz,
                                                      "seeg_pom_bin_in_mrielec_in_t1")

            last_job = job_coreg

        # Here we transform finally the pom coordinates to T1 space
        seeg_xyz_txt = File(MriElecSEEGCompFiles.SEEG_XYZ_TXT.value)
        seeg_in_t1_nii_gz = File(MriElecSEEGCompFiles.SEEG_IN_T1_VOL.value)
        trsfrm_job = Job(MriElecSEEGCompJobNames.TRANSFORM_MERIELEC_COORDS.value,
                         node_label="Transform seeg pom coordinates to T1 space")
        trsfrm_job.addArguments(seeg_pom_xyz_txt, seeg_pom_vol, t1_nii_gz, seeg_xyz_txt,
                                seeg_in_t1_nii_gz, seeg_pom_to_t1)
        trsfrm_job.uses(seeg_pom_xyz_txt, Link.INPUT)
        trsfrm_job.uses(seeg_pom_vol, Link.INPUT)
        trsfrm_job.uses(t1_nii_gz, Link.INPUT)
        trsfrm_job.uses(seeg_pom_to_t1, Link.INPUT)
        trsfrm_job.uses(seeg_xyz_txt, Link.OUTPUT, transfer=True, register=True)
        trsfrm_job.uses(seeg_in_t1_nii_gz, Link.OUTPUT, transfer=True, register=True)

        dax.addJob(trsfrm_job)
        dax.depends(trsfrm_job, last_job)

        self.qc_snapshots.add_2vols_snapshot_step(dax, [trsfrm_job], seeg_in_t1_nii_gz, t1_nii_gz, "seeg_in_t1")

        return trsfrm_job