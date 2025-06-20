# coding: utf-8
__author__ = 'Roman Solovyev (ZFTurbo): https://github.com/ZFTurbo/'

import argparse
import numpy as np
import torch
import torch.nn as nn
import yaml
import os
import soundfile as sf
from ml_collections import ConfigDict
from omegaconf import OmegaConf
from tqdm.auto import tqdm
from typing import Dict, List, Tuple, Any, Union
from models.preprocess import STFT, HTDemucs_processor, BS_roformer_processor, Mel_band_roformer_processor, SCNet_processor
import loralib as lora
import onnxruntime as ort
import tensorrt as trt
import pycuda.driver as cuda
# from tensorrt_engine import Engine

def load_config(model_type: str, config_path: str) -> Union[ConfigDict, OmegaConf]:
    """
    Load the configuration from the specified path based on the model type.

    Parameters:
    ----------
    model_type : str
        The type of model to load (e.g., 'htdemucs', 'mdx23c', etc.).
    config_path : str
        The path to the YAML or OmegaConf configuration file.

    Returns:
    -------
    config : Any
        The loaded configuration, which can be in different formats (e.g., OmegaConf or ConfigDict).

    Raises:
    ------
    FileNotFoundError:
        If the configuration file at `config_path` is not found.
    ValueError:
        If there is an error loading the configuration file.
    """
    try:
        with open(config_path, 'r') as f:
            if model_type == 'htdemucs' or model_type == 'my_htdemucs':
                config = OmegaConf.load(config_path)
            else:
                config = ConfigDict(yaml.load(f, Loader=yaml.FullLoader))
            return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")


def get_model_from_config(model_type: str, config_path: str) -> Tuple:
    """
    Load the model specified by the model type and configuration file.

    Parameters:
    ----------
    model_type : str
        The type of model to load (e.g., 'mdx23c', 'htdemucs', 'scnet', etc.).
    config_path : str
        The path to the configuration file (YAML or OmegaConf format).

    Returns:
    -------
    model : nn.Module or None
        The initialized model based on the `model_type`, or None if the model type is not recognized.
    config : Any
        The configuration used to initialize the model. This could be in different formats
        depending on the model type (e.g., OmegaConf, ConfigDict).

    Raises:
    ------
    ValueError:
        If the `model_type` is unknown or an error occurs during model initialization.
    """

    config = load_config(model_type, config_path)

    if model_type == 'mdx23c':
        from models.mdx23c_tfc_tdf_v3 import TFC_TDF_net
        model = TFC_TDF_net(config)
    elif model_type == 'my_mdx23c':
        from models_without_stft.mdx23c_tfc_tdf_v3_no_stft import TFC_TDF_net
        model = TFC_TDF_net(config)
    elif model_type == 'htdemucs':
        from models.demucs4ht import get_model
        model = get_model(config)
    elif model_type == 'my_htdemucs':
        from models_without_stft.demucs4ht_no_stft import get_model
        model = get_model(config)
    elif model_type == 'segm_models':
        from models.segm_models import Segm_Models_Net
        model = Segm_Models_Net(config)
    elif model_type == 'my_segm_models':
        from models_without_stft.segm_models_no_stft import Segm_Models_Net
        model = Segm_Models_Net(config)
    elif model_type == 'torchseg':
        from models.torchseg_models import Torchseg_Net
        model = Torchseg_Net(config)
    elif model_type == 'mel_band_roformer':
        from models.bs_roformer import MelBandRoformer
        model = MelBandRoformer(**dict(config.model))
    elif model_type == 'my_mel_band_roformer':
        from models_without_stft.mel_band_roformer_no_stft import MelBandRoformer
        model = MelBandRoformer(**dict(config.model))
    elif model_type == 'mel_band_roformer_experimental':
        from models.bs_roformer.mel_band_roformer_experimental import MelBandRoformer
        model = MelBandRoformer(**dict(config.model))
    elif model_type == 'bs_roformer':
        from models.bs_roformer import BSRoformer
        model = BSRoformer(**dict(config.model))
    elif model_type == 'my_bs_roformer':
        from models_without_stft.bs_roformer_no_stft import BSRoformer
        model = BSRoformer(**dict(config.model))
    elif model_type == 'bs_roformer_experimental':
        from models.bs_roformer.bs_roformer_experimental import BSRoformer
        model = BSRoformer(**dict(config.model))
    elif model_type == 'swin_upernet':
        from models.upernet_swin_transformers import Swin_UperNet_Model
        model = Swin_UperNet_Model(config)
    elif model_type == 'bandit':
        from models.bandit.core.model import MultiMaskMultiSourceBandSplitRNNSimple
        model = MultiMaskMultiSourceBandSplitRNNSimple(**config.model)
    elif model_type == 'bandit_v2':
        from models.bandit_v2.bandit import Bandit
        model = Bandit(**config.kwargs)
    elif model_type == 'scnet_unofficial':
        from models.scnet_unofficial import SCNet
        model = SCNet(**config.model)
    elif model_type == 'scnet':
        from models.scnet import SCNet
        model = SCNet(**config.model)
    elif model_type == 'scnet_tran':
        from models.scnet.scnet_tran import SCNet_Tran
        model = SCNet_Tran(**config.model)
    elif model_type == 'apollo':
        from models.look2hear.models import BaseModel
        model = BaseModel.apollo(**config.model)
    elif model_type == 'bs_mamba2':
        from models.ts_bs_mamba2 import Separator
        model = Separator(**config.model)
    elif model_type == 'experimental_mdx23c_stht':
        from models.mdx23c_tfc_tdf_v3_with_STHT import TFC_TDF_net
        model = TFC_TDF_net(config)
    # elif model_type == 'myscnet':
    #     from models.scnet.my_scnet import SCNet_encoder, SCNet_decoder не очень полезно импортировать в ONNX
    #     model = [SCNet_encoder(config), SCNet_decoder(config)]
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    return model, config


def read_audio_transposed(path: str, instr: str = None, skip_err: bool = False) -> Tuple[np.ndarray, int]:
    """
    Reads an audio file, ensuring mono audio is converted to two-dimensional format,
    and transposes the data to have channels as the first dimension.
    Parameters
    ----------
    path : str
        Path to the audio file.
    skip_err: bool
        If true, not raise errors
    instr:
        name of instument
    Returns
    -------
    Tuple[np.ndarray, int]
        A tuple containing:
        - Transposed audio data as a NumPy array with shape (channels, length).
          For mono audio, the shape will be (1, length).
        - Sampling rate (int), e.g., 44100.
    """

    try:
        mix, sr = sf.read(path)
    except Exception as e:
        if skip_err:
            print(f"No stem {instr}: skip!")
            return None, None
        else:
            raise RuntimeError(f"Error reading the file at {path}: {e}")
    else:
        if len(mix.shape) == 1:  # For mono audio
            mix = np.expand_dims(mix, axis=-1)
        return mix.T, sr


def normalize_audio(audio: np.ndarray) -> tuple[np.ndarray, Dict[str, float]]:
    """
    Normalize an audio signal by subtracting the mean and dividing by the standard deviation.

    Parameters:
    ----------
    audio : np.ndarray
        Input audio array with shape (channels, time) or (time,).

    Returns:
    -------
    tuple[np.ndarray, dict[str, float]]
        - Normalized audio array with the same shape as the input.
        - Dictionary containing the mean and standard deviation of the original audio.
    """

    mono = audio.mean(0)
    mean, std = mono.mean(), mono.std()
    return (audio - mean) / std, {"mean": mean, "std": std}


def denormalize_audio(audio: np.ndarray, norm_params: Dict[str, float]) -> np.ndarray:
    """
    Denormalize an audio signal by reversing the normalization process (multiplying by the standard deviation
    and adding the mean).

    Parameters:
    ----------
    audio : np.ndarray
        Normalized audio array to be denormalized.
    norm_params : dict[str, float]
        Dictionary containing the 'mean' and 'std' values used for normalization.

    Returns:
    -------
    np.ndarray
        Denormalized audio array with the same shape as the input.
    """

    return audio * norm_params["std"] + norm_params["mean"]


def apply_tta(
        config,
        model: torch.nn.Module,
        mix: torch.Tensor,
        waveforms_orig: Dict[str, torch.Tensor],
        device: torch.device,
        model_type: str
) -> Dict[str, torch.Tensor]:
    """
    Apply Test-Time Augmentation (TTA) for source separation.

    This function processes the input mixture with test-time augmentations, including
    channel inversion and polarity inversion, to enhance the separation results. The
    results from all augmentations are averaged to produce the final output.

    Parameters:
    ----------
    config : Any
        Configuration object containing model and processing parameters.
    model : torch.nn.Module
        The trained model used for source separation.
    mix : torch.Tensor
        The mixed audio tensor with shape (channels, time).
    waveforms_orig : Dict[str, torch.Tensor]
        Dictionary of original separated waveforms (before TTA) for each instrument.
    device : torch.device
        Device (CPU or CUDA) on which the model will be executed.
    model_type : str
        Type of the model being used (e.g., "demucs", "custom_model").

    Returns:
    -------
    Dict[str, torch.Tensor]
        Updated dictionary of separated waveforms after applying TTA.
    """
    # Create augmentations: channel inversion and polarity inversion
    track_proc_list = [mix[::-1].copy(), -1.0 * mix.copy()]

    # Process each augmented mixture
    for i, augmented_mix in enumerate(track_proc_list):
        waveforms = demix(config, model, augmented_mix, device, model_type=model_type)
        for el in waveforms:
            if i == 0:
                waveforms_orig[el] += waveforms[el][::-1].copy()
            else:
                waveforms_orig[el] -= waveforms[el]

    # Average the results across augmentations
    for el in waveforms_orig:
        waveforms_orig[el] /= len(track_proc_list) + 1

    return waveforms_orig


def _getWindowingArray(window_size: int, fade_size: int) -> torch.Tensor:
    """
    Generate a windowing array with a linear fade-in at the beginning and a fade-out at the end.

    This function creates a window of size `window_size` where the first `fade_size` elements
    linearly increase from 0 to 1 (fade-in) and the last `fade_size` elements linearly decrease
    from 1 to 0 (fade-out). The middle part of the window is filled with ones.

    Parameters:
    ----------
    window_size : int
        The total size of the window.
    fade_size : int
        The size of the fade-in and fade-out regions.

    Returns:
    -------
    torch.Tensor
        A tensor of shape (window_size,) containing the generated windowing array.

    Example:
    -------
    If `window_size=10` and `fade_size=3`, the output will be:
    tensor([0.0000, 0.5000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 0.5000, 0.0000])
    """

    fadein = torch.linspace(0, 1, fade_size)
    fadeout = torch.linspace(1, 0, fade_size)

    window = torch.ones(window_size)
    window[-fade_size:] = fadeout
    window[:fade_size] = fadein
    return window


def demix(
    config: ConfigDict,
    model: Union[torch.nn.Module, Any],
    mix: Union[torch.Tensor, np.ndarray],
    device: torch.device,
    model_type: str,
    pbar: bool = False,
    use_onnx: bool = False, 
    use_tensorrt: bool = False,
    use_compile: bool = False
) -> Dict[str, np.ndarray]:
    """
    Unified function for audio source separation with support for both PyTorch and ONNX models.

    Parameters:
    ----------
    config : ConfigDict
        Model configuration
    model : Union[torch.nn.Module, Any]
        PyTorch model or ONNX session
    mix : Union[torch.Tensor, np.ndarray]
        Input mixture audio
    device : torch.device
        Device to use for inference
    model_type : str
        Type of model ('htdemucs', 'bs_roformer', 'mel_band_roformer', etc.)
    pbar : bool
        Whether to show progress bar
    use_onnx : bool
        Whether to use ONNX model

    Returns:
    -------
    Dict[str, np.ndarray]
        Dictionary of separated sources
    """

    mix = torch.tensor(mix, dtype=torch.float32)
    preprocessor = None
    mode = 'generic'
    if use_tensorrt:
        import pycuda.autoinit

    if use_onnx or use_tensorrt or use_compile:
        if model_type == 'htdemucs':
            mode = 'demucs'
            preprocessor = HTDemucs_processor(config)
        elif model_type == 'bs_roformer':
            preprocessor = BS_roformer_processor(**dict(config.model))
        elif model_type == 'mel_band_roformer':
            preprocessor = Mel_band_roformer_processor(**dict(config.model))
        else:
            preprocessor = STFT(config.audio)
    # Define processing parameters based on the mode
    if mode == 'demucs':
        chunk_size = config.training.samplerate * config.training.segment
        num_instruments = len(config.training.instruments)
        num_overlap = config.inference.num_overlap
        step = chunk_size // num_overlap
    else:
        chunk_size = config.audio.chunk_size
        num_instruments = len(prefer_target_instrument(config))
        num_overlap = config.inference.num_overlap

        fade_size = chunk_size // 10
        step = chunk_size // num_overlap
        border = chunk_size - step
        length_init = mix.shape[-1]
        windowing_array = _getWindowingArray(chunk_size, fade_size)
        # Add padding for generic mode to handle edge artifacts
        if length_init > 2 * border and border > 0:
            mix = nn.functional.pad(mix, (border, border), mode="reflect")

    batch_size = config.inference.batch_size

    use_amp = getattr(config.training, 'use_amp', True)

    with torch.cuda.amp.autocast(enabled=use_amp):
        with torch.inference_mode():
            # Initialize result and counter tensors
            req_shape = (num_instruments,) + mix.shape
            result = torch.zeros(req_shape, dtype=torch.float32).to(device)
            counter = torch.zeros(req_shape, dtype=torch.float32).to(device)

            i = 0
            batch_data = []
            batch_locations = []
            progress_bar = tqdm(
                total=mix.shape[1], desc="Processing audio chunks", leave=False
            ) if pbar else None

            while i < mix.shape[1]:
                # Extract chunk and apply padding if necessary
                part = mix[:, i:i + chunk_size].to(device)
                chunk_len = part.shape[-1]
                if mode == "generic" and chunk_len > chunk_size // 2:
                    pad_mode = "reflect"
                else:
                    pad_mode = "constant"
                part = nn.functional.pad(part, (0, chunk_size - chunk_len), mode=pad_mode, value=0)

                batch_data.append(part)
                batch_locations.append((i, chunk_len))
                i += step

                # Process batch if it's full or the end is reached
                if len(batch_data) >= batch_size or i >= mix.shape[1]:
                    arr = torch.stack(batch_data, dim=0)
                    if use_onnx:
                        if model_type == 'htdemucs':
                            x = preprocessor.stft(arr).cpu().numpy()
                            arr = arr.cpu().numpy()
                            inputs = {
                                model.get_inputs()[0].name: x,
                                model.get_inputs()[1].name: arr
                            }
                            output = model.run(None, inputs)
                            x = preprocessor.istft(torch.tensor(output[0]).to(device), torch.tensor(output[1]).to(device))
                        else:
                            x = preprocessor.stft(arr)
                            x = torch.tensor(model.run(None, {model.get_inputs()[0].name: x.cpu().numpy()})[0]).to(device)
                            x = preprocessor.istft(x)
                    elif use_tensorrt:
                        if model_type == 'htdemucs':
                            bindings = list()
                            x = preprocessor.stft(arr).cpu().numpy()
                            arr = arr.cpu().numpy()
                            context = model.create_execution_context()
                            
                            input_tensor_name = model.get_tensor_name(0)
                            context.set_input_shape(input_tensor_name, x.shape)
                            d_input1 = cuda.mem_alloc(x.nbytes)
                            cuda.memcpy_htod(d_input1, x)
                            
                            input_tensor_name = model.get_tensor_name(1)
                            context.set_input_shape(input_tensor_name, arr.shape)
                            d_input2 = cuda.mem_alloc(arr.nbytes)
                            cuda.memcpy_htod(d_input2, arr)
                            
                            output_tensor_name = model.get_tensor_name(2)
                            output_tensor_shape = context.get_tensor_shape(output_tensor_name)
                            output_size = trt.volume(output_tensor_shape) * np.dtype(np.float32).itemsize
                            d_output1 = cuda.mem_alloc(output_size)
                            output_data1 = np.empty(output_tensor_shape, dtype=np.float32)
                            
                            output_tensor_name = model.get_tensor_name(3)
                            output_tensor_shape = context.get_tensor_shape(output_tensor_name)
                            output_size = trt.volume(output_tensor_shape) * np.dtype(np.float32).itemsize
                            d_output2 = cuda.mem_alloc(output_size)
                            output_data2 = np.empty(output_tensor_shape, dtype=np.float32)
                            bindings = [int(d_input1), int(d_input2), int(d_output1), int(d_output2)]
                            
                            context.execute_v2(bindings)
                            
                            cuda.memcpy_dtoh(output_data1, d_output1)
                            cuda.memcpy_dtoh(output_data2, d_output2)
                            
                            x = preprocessor.istft(torch.tensor(output_data1).to(device), torch.tensor(output_data2).to(device))
                            
                            
                        else:
                            x = preprocessor.stft(arr).cpu().numpy()
                            context = model.create_execution_context()
                            input_tensor_name = model.get_tensor_name(0)
                            context.set_input_shape(input_tensor_name, x.shape)
                            output_tensor_name = model.get_tensor_name(1)
                            output_tensor_shape = context.get_tensor_shape(output_tensor_name)
                            output_size = trt.volume(output_tensor_shape) * np.dtype(np.float32).itemsize
                            d_input = cuda.mem_alloc(x.nbytes)
                            d_output = cuda.mem_alloc(output_size)
                            bindings = [int(d_input), int(d_output)]
                            cuda.memcpy_htod(d_input, x)
                            context.execute_v2(bindings)
                            output_data = np.empty(output_tensor_shape, dtype=np.float32)
                            cuda.memcpy_dtoh(output_data, d_output)
                            x = preprocessor.istft(torch.tensor(output_data).to(device))
                    elif use_compile:
                        if model_type == 'htdemucs':
                            x = preprocessor.stft(arr)
                            x, xt = model(x, arr)
                            x = preprocessor.istft(x, xt)
                        else:
                            x = preprocessor.stft(arr)
                            x = model(x)
                            x = preprocessor.istft(x)
                    else:
                        x = model(arr)

                    if mode == "generic":
                        window = windowing_array.clone() # using clone() fixes the clicks at chunk edges when using batch_size=1
                        if i - step == 0:  # First audio chunk, no fadein
                            window[:fade_size] = 1
                        elif i >= mix.shape[1]:  # Last audio chunk, no fadeout
                            window[-fade_size:] = 1

                    for j, (start, seg_len) in enumerate(batch_locations):
                        if mode == "generic":
                            result[..., start:start + seg_len] += x[j, ..., :seg_len].to(device) * window[..., :seg_len].to(device)
                            counter[..., start:start + seg_len] += window[..., :seg_len].to(device)
                        else:
                            result[..., start:start + seg_len] += x[j, ..., :seg_len].to(device)
                            counter[..., start:start + seg_len] += 1.0

                    batch_data.clear()
                    batch_locations.clear()

                if progress_bar:
                    progress_bar.update(step)

            if progress_bar:
                progress_bar.close()

            # Compute final estimated sources
            estimated_sources = result / counter
            estimated_sources = estimated_sources.cpu().numpy()
            np.nan_to_num(estimated_sources, copy=False, nan=0.0)

            # Remove padding for generic mode
            if mode == "generic":
                if length_init > 2 * border and border > 0:
                    estimated_sources = estimated_sources[..., border:-border]

    # Return the result as a dictionary or a single array
    if mode == "demucs":
        instruments = config.training.instruments
    else:
        instruments = prefer_target_instrument(config)

    ret_data = {k: v for k, v in zip(instruments, estimated_sources)}

    if mode == "demucs" and num_instruments <= 1:
        return estimated_sources
    else:
        return ret_data


def prefer_target_instrument(config: ConfigDict) -> List[str]:
    """
        Return the list of target instruments based on the configuration.
        If a specific target instrument is specified in the configuration,
        it returns a list with that instrument. Otherwise, it returns the list of instruments.

        Parameters:
        ----------
        config : ConfigDict
            Configuration object containing the list of instruments or the target instrument.

        Returns:
        -------
        List[str]
            A list of target instruments.
        """
    if getattr(config.training, 'target_instrument', None):
        return [config.training.target_instrument]
    else:
        return config.training.instruments


def load_not_compatible_weights(model: torch.nn.Module, weights: str, verbose: bool = False) -> None:
    """
    Load weights into a model, handling mismatched shapes and dimensions.

    Args:
        model: PyTorch model into which the weights will be loaded.
        weights: Path to the weights file.
        verbose: If True, prints detailed information about matching and mismatched layers.
    """

    new_model = model.state_dict()
    old_model = torch.load(weights)
    if 'state' in old_model:
        # Fix for htdemucs weights loading
        old_model = old_model['state']
    if 'state_dict' in old_model:
        # Fix for apollo weights loading
        old_model = old_model['state_dict']

    for el in new_model:
        if el in old_model:
            if verbose:
                print(f'Match found for {el}!')
            if new_model[el].shape == old_model[el].shape:
                if verbose:
                    print('Action: Just copy weights!')
                new_model[el] = old_model[el]
            else:
                if len(new_model[el].shape) != len(old_model[el].shape):
                    if verbose:
                        print('Action: Different dimension! Too lazy to write the code... Skip it')
                else:
                    if verbose:
                        print(f'Shape is different: {tuple(new_model[el].shape)} != {tuple(old_model[el].shape)}')
                    ln = len(new_model[el].shape)
                    max_shape = []
                    slices_old = []
                    slices_new = []
                    for i in range(ln):
                        max_shape.append(max(new_model[el].shape[i], old_model[el].shape[i]))
                        slices_old.append(slice(0, old_model[el].shape[i]))
                        slices_new.append(slice(0, new_model[el].shape[i]))
                    # print(max_shape)
                    # print(slices_old, slices_new)
                    slices_old = tuple(slices_old)
                    slices_new = tuple(slices_new)
                    max_matrix = np.zeros(max_shape, dtype=np.float32)
                    for i in range(ln):
                        max_matrix[slices_old] = old_model[el].cpu().numpy()
                    max_matrix = torch.from_numpy(max_matrix)
                    new_model[el] = max_matrix[slices_new]
        else:
            if verbose:
                print(f'Match not found for {el}!')
    model.load_state_dict(
        new_model
    )


def load_lora_weights(model: torch.nn.Module, lora_path: str, device: str = 'cpu') -> None:
    """
    Load LoRA weights into a model.
    This function updates the given model with LoRA-specific weights from the specified checkpoint file.
    It does not require the checkpoint to match the model's full state dictionary, as only LoRA layers are updated.

    Parameters:
    ----------
    model : Module
        The PyTorch model into which the LoRA weights will be loaded.
    lora_path : str
        Path to the LoRA checkpoint file.
    device : str, optional
        The device to load the weights onto, by default 'cpu'. Common values are 'cpu' or 'cuda'.

    Returns:
    -------
    None
        The model is updated in place.
    """
    lora_state_dict = torch.load(lora_path, map_location=device)
    model.load_state_dict(lora_state_dict, strict=False)


def load_start_checkpoint(args: argparse.Namespace, model: torch.nn.Module, type_='train') -> None:
    """
    Load the starting checkpoint for a model.

    Args:
        args: Parsed command-line arguments containing the checkpoint path.
        model: PyTorch model to load the checkpoint into.
        type_: how to load weights - for train we can load not fully compatible weights
    """

    print(f'Start from checkpoint: {args.start_check_point}')
    if type_ in ['train']:
        if 1:
            load_not_compatible_weights(model, args.start_check_point, verbose=False)
        else:
            model.load_state_dict(torch.load(args.start_check_point))
    else:
        device='cpu'
        if args.model_type in ['htdemucs', 'apollo']:
            state_dict = torch.load(args.start_check_point, map_location=device, weights_only=False)
            # Fix for htdemucs pretrained models
            if 'state' in state_dict:
                state_dict = state_dict['state']
            # Fix for apollo pretrained models
            if 'state_dict' in state_dict:
                state_dict = state_dict['state_dict']
        else:
            state_dict = torch.load(args.start_check_point, map_location=device, weights_only=True)
        model.load_state_dict(state_dict)

    if args.lora_checkpoint:
        print(f"Loading LoRA weights from: {args.lora_checkpoint}")
        load_lora_weights(model, args.lora_checkpoint)


def bind_lora_to_model(config: Dict[str, Any], model: nn.Module) -> nn.Module:
    """
    Replaces specific layers in the model with LoRA-extended versions.

    Parameters:
    ----------
    config : Dict[str, Any]
        Configuration containing parameters for LoRA. It should include a 'lora' key with parameters for `MergedLinear`.
    model : nn.Module
        The original model in which the layers will be replaced.

    Returns:
    -------
    nn.Module
        The modified model with the replaced layers.
    """

    if 'lora' not in config:
        raise ValueError("Configuration must contain the 'lora' key with parameters for LoRA.")

    replaced_layers = 0  # Counter for replaced layers

    for name, module in model.named_modules():
        hierarchy = name.split('.')
        layer_name = hierarchy[-1]

        # Check if this is the target layer to replace (and layer_name == 'to_qkv')
        if isinstance(module, nn.Linear):
            try:
                # Get the parent module
                parent_module = model
                for submodule_name in hierarchy[:-1]:
                    parent_module = getattr(parent_module, submodule_name)

                # Replace the module with LoRA-enabled layer
                setattr(
                    parent_module,
                    layer_name,
                    lora.MergedLinear(
                        in_features=module.in_features,
                        out_features=module.out_features,
                        bias=module.bias is not None,
                        **config['lora']
                    )
                )
                replaced_layers += 1  # Increment the counter

            except Exception as e:
                print(f"Error replacing layer {name}: {e}")

    if replaced_layers == 0:
        print("Warning: No layers were replaced. Check the model structure and configuration.")
    else:
        print(f"Number of layers replaced with LoRA: {replaced_layers}")

    return model


def load_onnx_model(model_path: str, device: str = 'cpu') -> Any:
    """
    Load ONNX model and create inference session.

    Parameters:
    ----------
    model_path : str
        Path to ONNX model file
    device : str
        Device to use for inference ('cpu' or 'cuda')

    Returns:
    -------
    onnxruntime.InferenceSession
        ONNX inference session
    """
    session_options = ort.SessionOptions()
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    
    if 'cuda' in device:
        providers = [
            'CUDAExecutionProvider'
        ]
    else:
        providers = ['CPUExecutionProvider']
    print(providers, device)
    try:
        # Create inference session
        session = ort.InferenceSession(
            model_path,
            providers=providers,
            sess_options=session_options
        )
        
        return session
        
    except Exception as e:
        raise RuntimeError(f"Failed to load ONNX model from {model_path}: {str(e)}")


def load_engine_model(model_path: str) -> Any:
    """
    """
    logger = trt.Logger(trt.Logger.WARNING)
    with open(model_path, "rb") as f, trt.Runtime(logger) as runtime:
        engine = runtime.deserialize_cuda_engine(f.read())
    print(type(engine))
    return engine

def draw_spectrogram(waveform, sample_rate, length, output_file):
    import librosa.display

    # Cut only required part of spectorgram
    x = waveform[:int(length * sample_rate), :]
    X = librosa.stft(x.mean(axis=-1))  # perform short-term fourier transform on mono signal
    Xdb = librosa.amplitude_to_db(np.abs(X), ref=np.max)  # convert an amplitude spectrogram to dB-scaled spectrogram.
    fig, ax = plt.subplots()
    # plt.figure(figsize=(30, 10))  # initialize the fig size
    img = librosa.display.specshow(
        Xdb,
        cmap='plasma',
        sr=sample_rate,
        x_axis='time',
        y_axis='linear',
        ax=ax
    )
    ax.set(title='File: ' + os.path.basename(output_file))
    fig.colorbar(img, ax=ax, format="%+2.f dB")
    if output_file is not None:
        plt.savefig(output_file)
